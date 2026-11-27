"""Explicit composition path for a future approved authentication deployment.

Nothing in the operational API imports or calls this builder. It requires a
release-gate evidence object, real policies, secure browser settings, and a
request-scoped SQLAlchemy Session supplied by its caller.
"""

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, FastAPI, Request
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.api.v1.routes.authentication import (
    AuthCookieConfiguration,
    AuthRequestLimits,
    AuthRouteServices,
    CsrfValidator,
    HmacDoubleSubmitCsrf,
    TrustedOriginPolicy,
    build_auth_router,
    require_authenticated_csrf,
)
from app.api.v1.routes.inventory_writes import build_inventory_write_router
from app.core.auth_runtime import (
    AuthenticationActivationEvidence,
    AuthenticationRuntimeConfiguration,
    InventoryWriteActivationEvidence,
    assert_authentication_activation_ready,
    assert_inventory_writes_ready,
)
from app.core.authentication import (
    Principal,
    RolePermissionPolicy,
    authenticated_principal,
    principal_for_local_user,
)
from app.core.credential_verification import (
    CredentialVerificationService,
    DummyVerificationCredential,
    UsernameCanonicalizer,
)
from app.core.database_policies import DatabaseInventoryWritePolicy, ResourceScopePolicy
from app.core.errors import AppError
from app.core.login_orchestration import (
    AuthenticationCompletionPolicy,
    LoginAttemptProtection,
    LoginInputPolicy,
    LoginLogoutOrchestrator,
)
from app.core.operational_policies import (
    ApprovedRepairCurrencyPolicy,
    WorkflowApprovalConfiguration,
)
from app.core.password_hashing import PasswordHashBackend, PasswordHashingService
from app.core.permission_policy import ExplicitRolePermissionPolicy
from app.core.sessions import (
    SessionLifecycleService,
    SessionPolicy,
    SessionRejected,
    SessionServiceUnavailable,
    ValidatedSession,
)
from app.db.auth_repositories import (
    SqlAlchemyAccountSessionStateRepository,
    SqlAlchemyPasswordCredentialRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserIdentityRepository,
)
from app.services.inventory_writes import InventoryWritePolicy


def build_approved_database_auth_router(
    *,
    database_session_dependency: Callable[..., object],
    configuration: AuthenticationRuntimeConfiguration,
    evidence: AuthenticationActivationEvidence,
    password_backend: PasswordHashBackend,
    username_predicate: Callable[[str], ColumnElement[bool]],
    canonicalize_username: UsernameCanonicalizer,
    dummy_credential: DummyVerificationCredential,
    session_policy: SessionPolicy,
    login_input_policy: LoginInputPolicy,
    attempt_protection: LoginAttemptProtection,
    completion_policy: AuthenticationCompletionPolicy,
    cookie: AuthCookieConfiguration,
    origins: TrustedOriginPolicy,
    csrf: CsrfValidator,
    request_limits: AuthRequestLimits,
    clock: Callable[[], datetime],
):
    """Production entry point; retain all release checks."""
    assert_authentication_activation_ready(configuration, evidence)
    return _reusable_build_database_auth_router(
        database_session_dependency=database_session_dependency,
        configuration=configuration,
        evidence=evidence,
        password_backend=password_backend,
        username_predicate=username_predicate,
        canonicalize_username=canonicalize_username,
        dummy_credential=dummy_credential,
        session_policy=session_policy,
        login_input_policy=login_input_policy,
        attempt_protection=attempt_protection,
        completion_policy=completion_policy,
        cookie=cookie,
        origins=origins,
        csrf=csrf,
        request_limits=request_limits,
        clock=clock,
    )


def _reusable_build_database_auth_router(
    *,
    database_session_dependency: Callable[..., object],
    configuration: AuthenticationRuntimeConfiguration,
    evidence: AuthenticationActivationEvidence,
    password_backend: PasswordHashBackend,
    username_predicate: Callable[[str], ColumnElement[bool]],
    canonicalize_username: UsernameCanonicalizer,
    dummy_credential: DummyVerificationCredential,
    session_policy: SessionPolicy,
    login_input_policy: LoginInputPolicy,
    attempt_protection: LoginAttemptProtection,
    completion_policy: AuthenticationCompletionPolicy,
    cookie: AuthCookieConfiguration,
    origins: TrustedOriginPolicy,
    csrf: CsrfValidator,
    request_limits: AuthRequestLimits,
    clock: Callable[[], datetime],
):
    """Compose existing services/adapters after release evidence; never self-register."""

    if not isinstance(csrf, HmacDoubleSubmitCsrf):
        raise ValueError("Operational authentication requires the HMAC CSRF implementation.")
    if (
        configuration.cookie_name != cookie.name
        or configuration.same_site != cookie.same_site
        or configuration.cookie_max_age_seconds != cookie.max_age_cap_seconds
        or not origins.matches_configuration(configuration.trusted_origins)
        or origins.allows_missing_safe_origin
        or configuration.csrf_signing_key is None
        or configuration.csrf_token_lifetime_seconds is None
        or not csrf.matches_configuration(
            signing_key=configuration.csrf_signing_key.get_secret_value().encode("utf-8"),
            auth_cookie_name=cookie.name,
            lifetime=configuration.csrf_token_lifetime_seconds,
        )
    ):
        raise ValueError("Authentication runtime settings do not match the approved browser boundary.")

    def request_services(session: Session = Depends(database_session_dependency)) -> AuthRouteServices:
        credential_service = CredentialVerificationService(
            users=SqlAlchemyUserIdentityRepository(
                session, username_predicate=username_predicate
            ),
            credentials=SqlAlchemyPasswordCredentialRepository(session),
            passwords=PasswordHashingService(password_backend),
            canonicalize_username=canonicalize_username,
            dummy_credential=dummy_credential,
        )
        session_service = SessionLifecycleService(
            sessions=SqlAlchemySessionRepository(session),
            accounts=SqlAlchemyAccountSessionStateRepository(session),
            policy=session_policy,
            clock=clock,
        )
        orchestration = LoginLogoutOrchestrator(
            credentials=credential_service,
            sessions=session_service,
            attempt_protection=attempt_protection,
            completion_policy=completion_policy,
            input_policy=login_input_policy,
        )
        return AuthRouteServices(orchestration=orchestration, sessions=session_service)

    return build_auth_router(
        orchestration=None,
        sessions=None,
        services_dependency=request_services,
        cookie=cookie,
        origins=origins,
        csrf=csrf,
        limits=request_limits,
        input_policy=login_input_policy,
        clock=clock,
    )


def build_cookie_principal_dependency(
    *,
    cookie_name: str,
    session_service_dependency: Callable[..., SessionLifecycleService],
    role_policy_dependency: Callable[..., RolePermissionPolicy],
    database_session_dependency: Callable[..., object],
):
    """Build an explicit cookie-session identity dependency for protected APIs.

    The dependency validates the current server-side session, then reloads the
    user's current account and role assignments. Candidate permission mappings
    remain the responsibility of an explicitly approved policy dependency.
    """
    if not isinstance(cookie_name, str) or not cookie_name.startswith("__Host-"):
        raise ValueError("Authentication cookie must use a host-only __Host- name.")

    def dependency(
        request: Request,
        sessions: SessionLifecycleService = Depends(session_service_dependency),
        policy: RolePermissionPolicy = Depends(role_policy_dependency),
        session: Session = Depends(database_session_dependency),
    ) -> Principal:
        token, malformed = _cookie_value(request, cookie_name)
        if malformed or not token:
            raise AppError("AUTHENTICATION_REQUIRED", "Authentication is required.", 401)
        try:
            verified = sessions.validate(token, update_activity=True)
        except SessionRejected:
            raise AppError("INVALID_CREDENTIALS", "Credentials are invalid or expired.", 401) from None
        except SessionServiceUnavailable:
            raise AppError("AUTHENTICATION_UNAVAILABLE", "Authentication is temporarily unavailable.", 503) from None
        except Exception:
            raise AppError("AUTHENTICATION_UNAVAILABLE", "Authentication is temporarily unavailable.", 503) from None
        if not isinstance(verified, ValidatedSession):
            raise AppError("AUTHENTICATION_UNAVAILABLE", "Authentication is temporarily unavailable.", 503)
        return principal_for_local_user(verified.user_id, session, policy)

    return dependency


def build_session_service_dependency(
    *,
    database_session_dependency: Callable[..., object],
    session_policy: SessionPolicy,
    clock: Callable[[], datetime],
):
    """Provide a fresh session lifecycle service over the request's DB session."""
    def dependency(session: Session = Depends(database_session_dependency)) -> SessionLifecycleService:
        return SessionLifecycleService(
            sessions=SqlAlchemySessionRepository(session),
            accounts=SqlAlchemyAccountSessionStateRepository(session),
            policy=session_policy,
            clock=clock,
        )

    return dependency


def build_approved_role_permission_policy() -> RolePermissionPolicy:
    """Return the closed catalog mapping; role rows still require explicit assignment."""
    return ExplicitRolePermissionPolicy()


def build_database_inventory_write_policy_dependency(
    *,
    principal_dependency: Callable[..., Principal],
    database_session_dependency: Callable[..., object],
    role_policy_dependency: Callable[..., RolePermissionPolicy],
    resource_scope_dependency: Callable[..., ResourceScopePolicy],
    approval_configuration: WorkflowApprovalConfiguration,
    repair_currency_policy: ApprovedRepairCurrencyPolicy,
):
    """Compose current actor, current role state, explicit scope and workflow rules."""
    def dependency(
        principal: Principal = Depends(principal_dependency),
        session: Session = Depends(database_session_dependency),
        role_policy: RolePermissionPolicy = Depends(role_policy_dependency),
        resource_scope: ResourceScopePolicy = Depends(resource_scope_dependency),
    ) -> InventoryWritePolicy:
        return DatabaseInventoryWritePolicy(
            session=session,
            actor=principal,
            role_policy=role_policy,
            resource_scope=resource_scope,
            approval_configuration=approval_configuration,
            repair_currency_codes=repair_currency_policy.codes,
        )

    return dependency


def build_approved_inventory_write_router(
    *,
    database_session_dependency: Callable[..., object],
    configuration: AuthenticationRuntimeConfiguration,
    evidence: AuthenticationActivationEvidence,
    inventory_write_evidence: InventoryWriteActivationEvidence,
    cookie_name: str,
    origins: TrustedOriginPolicy,
    csrf: CsrfValidator,
    csrf_header_max_bytes: int,
    role_policy_dependency: Callable[..., RolePermissionPolicy],
    write_policy_dependency: Callable[..., InventoryWritePolicy],
    session_policy: SessionPolicy,
    clock: Callable[[], datetime],
):
    """Production entry point; retain all release checks."""
    assert_authentication_activation_ready(configuration, evidence)
    assert_inventory_writes_ready(inventory_write_evidence)
    return _reusable_build_inventory_write_router(
        database_session_dependency=database_session_dependency,
        configuration=configuration,
        evidence=evidence,
        inventory_write_evidence=inventory_write_evidence,
        cookie_name=cookie_name,
        origins=origins,
        csrf=csrf,
        csrf_header_max_bytes=csrf_header_max_bytes,
        role_policy_dependency=role_policy_dependency,
        write_policy_dependency=write_policy_dependency,
        session_policy=session_policy,
        clock=clock,
    )


def _reusable_build_inventory_write_router(
    *,
    database_session_dependency: Callable[..., object],
    configuration: AuthenticationRuntimeConfiguration,
    evidence: AuthenticationActivationEvidence,
    inventory_write_evidence: InventoryWriteActivationEvidence,
    cookie_name: str,
    origins: TrustedOriginPolicy,
    csrf: CsrfValidator,
    csrf_header_max_bytes: int,
    role_policy_dependency: Callable[..., RolePermissionPolicy],
    write_policy_dependency: Callable[..., InventoryWritePolicy],
    session_policy: SessionPolicy,
    clock: Callable[[], datetime],
):
    """Build (but never register) inventory writes after the auth release gate."""
    if not isinstance(csrf, HmacDoubleSubmitCsrf):
        raise ValueError("Operational inventory writes require the configured HMAC CSRF implementation.")
    if (
        configuration.cookie_name != cookie_name
        or not origins.matches_configuration(configuration.trusted_origins)
        or origins.allows_missing_safe_origin
        or configuration.csrf_signing_key is None
        or configuration.csrf_token_lifetime_seconds is None
        or not csrf.matches_configuration(
            signing_key=configuration.csrf_signing_key.get_secret_value().encode("utf-8"),
            auth_cookie_name=cookie_name,
            lifetime=configuration.csrf_token_lifetime_seconds,
        )
    ):
        raise ValueError("Inventory write runtime settings do not match the approved browser boundary.")
    session_dependency = build_session_service_dependency(
        database_session_dependency=database_session_dependency,
        session_policy=session_policy,
        clock=clock,
    )
    principal_dependency = build_cookie_principal_dependency(
        cookie_name=cookie_name,
        session_service_dependency=session_dependency,
        role_policy_dependency=role_policy_dependency,
        database_session_dependency=database_session_dependency,
    )
    return build_inventory_write_router(
        principal_dependency=principal_dependency,
        session_dependency=database_session_dependency,
        write_policy_dependency=write_policy_dependency,
        csrf_dependency=require_authenticated_csrf(
            origins=origins, csrf=csrf, max_header_bytes=csrf_header_max_bytes,
        ),
    )


def build_approved_inventory_cookie_principal_override(
    *,
    database_session_dependency: Callable[..., object],
    configuration: AuthenticationRuntimeConfiguration,
    evidence: AuthenticationActivationEvidence,
    cookie_name: str,
    role_policy_dependency: Callable[..., RolePermissionPolicy],
    session_policy: SessionPolicy,
    clock: Callable[[], datetime],
):
    """Production entry point; retain all release checks."""
    assert_authentication_activation_ready(configuration, evidence)
    return _reusable_build_inventory_cookie_principal_override(
        database_session_dependency=database_session_dependency,
        configuration=configuration,
        evidence=evidence,
        cookie_name=cookie_name,
        role_policy_dependency=role_policy_dependency,
        session_policy=session_policy,
        clock=clock,
    )


def _reusable_build_inventory_cookie_principal_override(
    *,
    database_session_dependency: Callable[..., object],
    configuration: AuthenticationRuntimeConfiguration,
    evidence: AuthenticationActivationEvidence,
    cookie_name: str,
    role_policy_dependency: Callable[..., RolePermissionPolicy],
    session_policy: SessionPolicy,
    clock: Callable[[], datetime],
):
    """Return the authenticated-principal override for the existing protected read API.

    The caller must assign this to FastAPI's dependency_overrides only in an approved
    application composition. This function does not mutate or activate an app.
    """
    dependency = build_session_service_dependency(
        database_session_dependency=database_session_dependency,
        session_policy=session_policy,
        clock=clock,
    )
    return {
        authenticated_principal: build_cookie_principal_dependency(
            cookie_name=cookie_name,
            session_service_dependency=dependency,
            role_policy_dependency=role_policy_dependency,
            database_session_dependency=database_session_dependency,
        )
    }


def compose_approved_authentication_application(
    application: FastAPI,
    *,
    api_prefix: str,
    configuration: AuthenticationRuntimeConfiguration,
    evidence: AuthenticationActivationEvidence,
    inventory_write_evidence: InventoryWriteActivationEvidence,
    authentication_router: APIRouter,
    inventory_write_router: APIRouter,
    cookie_principal_overrides: dict[object, object],
) -> None:
    """Production entry point; retain all release checks."""
    assert_authentication_activation_ready(configuration, evidence)
    assert_inventory_writes_ready(inventory_write_evidence)
    return _reusable_compose_authentication_application(
        application=application,
        api_prefix=api_prefix,
        configuration=configuration,
        evidence=evidence,
        inventory_write_evidence=inventory_write_evidence,
        authentication_router=authentication_router,
        inventory_write_router=inventory_write_router,
        cookie_principal_overrides=cookie_principal_overrides,
    )


def _reusable_compose_authentication_application(
    application: FastAPI,
    *,
    api_prefix: str,
    configuration: AuthenticationRuntimeConfiguration,
    evidence: AuthenticationActivationEvidence,
    inventory_write_evidence: InventoryWriteActivationEvidence,
    authentication_router: APIRouter,
    inventory_write_router: APIRouter,
    cookie_principal_overrides: dict[object, object],
) -> None:
    """Mount explicitly built routers only after both independent release gates.

    This is a controlled composition hook, not an app startup default. Callers
    must first build the routers using the approved builders above, which validate
    the concrete cookie, Origin, CSRF, session, repository, and policy dependencies.
    """
    if not isinstance(application, FastAPI) or not api_prefix.startswith("/"):
        raise ValueError("Application and API prefix are invalid.")
    existing = {
        (route.path, method)
        for route in application.routes
        for method in (getattr(route, "methods", None) or ())
    }
    new_paths = [
        (f"{api_prefix}{route.path}", method)
        for router in (authentication_router, inventory_write_router)
        for route in router.routes
        for method in (getattr(route, "methods", None) or ())
    ]
    if existing.intersection(new_paths) or len(new_paths) != len(set(new_paths)):
        raise ValueError("Authentication or inventory-write routes are already registered.")
    application.dependency_overrides.update(cookie_principal_overrides)
    application.include_router(authentication_router, prefix=api_prefix)
    application.include_router(inventory_write_router, prefix=api_prefix)


def _cookie_value(request: Request, name: str) -> tuple[str | None, bool]:
    matches: list[str] = []
    for header in request.headers.getlist("cookie"):
        for item in header.split(";"):
            key, separator, value = item.strip().partition("=")
            if key == name:
                if (
                    not separator
                    or not value
                    or len(value) > 64
                    or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for char in value)
                ):
                    return None, True
                matches.append(value)
    return (matches[0], False) if len(matches) == 1 else (None, len(matches) > 1)
