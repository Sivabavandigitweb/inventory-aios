"""Explicit, isolated application composition for approved rehearsal checks.

This factory is never imported by the normal app startup. It accepts only the
dedicated local restore-check URL and still enforces both activation evidence
gates before mounting authentication or inventory-write routes.
"""

from collections.abc import Callable, Generator
from datetime import datetime

from fastapi import Depends, FastAPI
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.api.v1.authentication_wiring import (
    build_approved_database_auth_router,
    build_approved_inventory_cookie_principal_override,
    build_approved_inventory_write_router,
    build_database_inventory_write_policy_dependency,
    compose_approved_authentication_application,
)
from app.api.v1.routes.authentication import (
    AuthCookieConfiguration,
    AuthRequestLimits,
    HmacDoubleSubmitCsrf,
    TrustedOriginPolicy,
)
from app.api.v1.routes.inventory_summary import build_inventory_summary_router
from app.core.auth_runtime import (
    AuthenticationActivationEvidence,
    AuthenticationRuntimeConfiguration,
    InventoryWriteActivationEvidence,
    assert_authentication_activation_ready,
    assert_inventory_writes_ready,
    session_policy_from_configuration,
)
from app.core.authentication import authenticated_principal
from app.core.config import Settings
from app.core.credential_verification import (
    DummyVerificationCredential,
    UsernameCanonicalizer,
)
from app.core.database_policies import OrganizationWideInventoryAdminScopePolicy
from app.core.integration_test_config import require_isolated_test_url
from app.core.login_orchestration import LoginInputPolicy
from app.core.operational_policies import (
    ApprovedPasswordOnlyCompletionPolicy,
    ApprovedRepairCurrencyPolicy,
    WorkflowApprovalConfiguration,
)
from app.core.password_hashing import PasswordHashBackend
from app.core.permission_policy import ExplicitRolePermissionPolicy
from app.core.postgres_login_protection import (
    LoginProtectionPolicy,
    PostgresLoginAttemptProtection,
)
from app.core.sessions import SessionPolicy
from app.db.auth_repositories import postgres_lower_ascii_username_predicate
from app.db.session import create_database_engine, create_session_factory, get_db_session
from app.main import create_app
from app.services.inventory_summary import (
    InventorySummaryService,
    SQLAlchemyInventorySummaryProvider,
    SummaryExposurePolicy,
    SummaryScopePolicy,
)
from app.services.inventory_writes import InventoryWritePolicy


def build_isolated_integration_app(
    *,
    database_url: str,
    settings: Settings,
    authentication_configuration: AuthenticationRuntimeConfiguration,
    authentication_evidence: AuthenticationActivationEvidence,
    inventory_write_evidence: InventoryWriteActivationEvidence,
    password_backend: PasswordHashBackend,
    dummy_credential: DummyVerificationCredential,
    canonicalize_username: UsernameCanonicalizer,
    login_input_policy: LoginInputPolicy,
    attempt_hmac_key: bytes,
    request_limits: AuthRequestLimits,
    activity_update_interval_seconds: int,
    clock: Callable[[], datetime],
    summary_scope_policy: SummaryScopePolicy | None = None,
    summary_exposure_policy: SummaryExposurePolicy | None = None,
    summary_minimum_group_size: int | None = None,
) -> FastAPI:
    """Build the rehearsal app using the existing gated auth/write/summary builders.

    Callers must pass actual evidence and explicit test secrets/settings. No
    environment file is read here, and no release evidence is synthesized.
    """
    target = require_isolated_test_url(database_url)
    parsed = make_url(target)
    if parsed.password is not None:
        raise ValueError("Integration database URLs must use the configured PostgreSQL password file.")
    if settings.environment != "test" or settings.database_url != database_url:
        raise ValueError("The isolated app requires test settings for its guarded database URL.")
    if settings.frontend_origin not in authentication_configuration.trusted_origins:
        raise ValueError("Test frontend origin must exactly match the configured trusted origin.")

    # Fail before creating an Engine, and preserve the same gates as normal composition.
    assert_authentication_activation_ready(authentication_configuration, authentication_evidence)
    assert_inventory_writes_ready(inventory_write_evidence)

    engine = create_database_engine(settings)
    session_factory = create_session_factory(engine)

    def request_database_session() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    role_policy = ExplicitRolePermissionPolicy()

    def role_policy_dependency() -> ExplicitRolePermissionPolicy:
        return role_policy

    def resource_scope_dependency(
        session: Session = Depends(request_database_session),
    ) -> OrganizationWideInventoryAdminScopePolicy:
        return OrganizationWideInventoryAdminScopePolicy(
            session=session,
            role_policy=role_policy,
        )

    session_policy: SessionPolicy = session_policy_from_configuration(
        authentication_configuration,
        activity_update_interval_seconds=activity_update_interval_seconds,
    )
    cookie = AuthCookieConfiguration(
        name=authentication_configuration.cookie_name or "",
        same_site=authentication_configuration.same_site or "strict",
        max_age_cap_seconds=authentication_configuration.cookie_max_age_seconds or 0,
    )
    origins = TrustedOriginPolicy(
        allowed_origins=authentication_configuration.trusted_origins,
        allow_missing_safe_origin=False,
    )
    signing_key = authentication_configuration.csrf_signing_key
    csrf_lifetime = authentication_configuration.csrf_token_lifetime_seconds
    if signing_key is None or csrf_lifetime is None:
        engine.dispose()
        raise ValueError("Explicit CSRF key and token lifetime are required.")
    csrf = HmacDoubleSubmitCsrf(
        signing_key=signing_key.get_secret_value().encode("utf-8"),
        auth_cookie_name=cookie.name,
        max_age_seconds=csrf_lifetime,
        clock=clock,
    )
    attempt_protection = PostgresLoginAttemptProtection(
        session_factory=session_factory,
        hmac_key=attempt_hmac_key,
        policy=LoginProtectionPolicy(),
        clock=clock,
    )
    try:
        authentication_router = build_approved_database_auth_router(
            database_session_dependency=request_database_session,
            configuration=authentication_configuration,
            evidence=authentication_evidence,
            password_backend=password_backend,
            username_predicate=postgres_lower_ascii_username_predicate,
            canonicalize_username=canonicalize_username,
            dummy_credential=dummy_credential,
            session_policy=session_policy,
            login_input_policy=login_input_policy,
            attempt_protection=attempt_protection,
            completion_policy=ApprovedPasswordOnlyCompletionPolicy(),
            cookie=cookie,
            origins=origins,
            csrf=csrf,
            request_limits=request_limits,
            clock=clock,
        )
        principal_overrides = build_approved_inventory_cookie_principal_override(
            database_session_dependency=request_database_session,
            configuration=authentication_configuration,
            evidence=authentication_evidence,
            cookie_name=cookie.name,
            role_policy_dependency=role_policy_dependency,
            session_policy=session_policy,
            clock=clock,
        )
        principal_dependency = principal_overrides[authenticated_principal]
        write_policy_dependency: Callable[..., InventoryWritePolicy] = build_database_inventory_write_policy_dependency(
            principal_dependency=principal_dependency,
            database_session_dependency=request_database_session,
            role_policy_dependency=role_policy_dependency,
            resource_scope_dependency=resource_scope_dependency,
            approval_configuration=WorkflowApprovalConfiguration(),
            repair_currency_policy=ApprovedRepairCurrencyPolicy(),
        )
        inventory_write_router = build_approved_inventory_write_router(
            database_session_dependency=request_database_session,
            configuration=authentication_configuration,
            evidence=authentication_evidence,
            inventory_write_evidence=inventory_write_evidence,
            cookie_name=cookie.name,
            origins=origins,
            csrf=csrf,
            csrf_header_max_bytes=request_limits.max_csrf_header_bytes,
            role_policy_dependency=role_policy_dependency,
            write_policy_dependency=write_policy_dependency,
            session_policy=session_policy,
            clock=clock,
        )

        application = create_app(settings)
        application.dependency_overrides[get_db_session] = request_database_session
        compose_approved_authentication_application(
            application,
            api_prefix=settings.api_prefix,
            configuration=authentication_configuration,
            evidence=authentication_evidence,
            inventory_write_evidence=inventory_write_evidence,
            authentication_router=authentication_router,
            inventory_write_router=inventory_write_router,
            cookie_principal_overrides=principal_overrides,
        )
        summary_configuration = (
            summary_scope_policy,
            summary_exposure_policy,
            summary_minimum_group_size,
        )
        if any(value is not None for value in summary_configuration):
            if (
                summary_scope_policy is None
                or summary_exposure_policy is None
                or summary_minimum_group_size is None
                or summary_minimum_group_size < 1
            ):
                raise ValueError("Summary routes require the complete approved scope/exposure configuration.")

            def summary_service_dependency(session: Session = Depends(request_database_session)) -> InventorySummaryService:
                return InventorySummaryService(
                    provider=SQLAlchemyInventorySummaryProvider(
                        session=session,
                        minimum_group_size=summary_minimum_group_size,
                        exposure_policy=summary_exposure_policy,
                    ),
                    scopes=summary_scope_policy,
                )

            summary_router = build_inventory_summary_router(
                service_dependency=summary_service_dependency,
                principal_dependency=principal_dependency,
            )
            existing = {route.path for route in application.routes}
            summary_paths = {f"{settings.api_prefix}{route.path}" for route in summary_router.routes}
            if existing.intersection(summary_paths):
                raise ValueError("Inventory summary route is already registered.")
            application.include_router(summary_router, prefix=settings.api_prefix)
        application.add_event_handler("shutdown", engine.dispose)
        return application
    except Exception:
        engine.dispose()
        raise
