from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.integration_application import build_isolated_integration_app
from app.api.v1.routes.inventory_summary import build_inventory_summary_router
from app.core.auth_runtime import (
    AuthenticationActivationEvidence,
    AuthenticationNotReady,
    AuthenticationRuntimeConfiguration,
    InventoryWriteActivationEvidence,
)
from app.core.authentication import Principal
from app.core.config import Settings
from app.core.database_policies import OrganizationWideInventoryAdminScopePolicy
from app.core.permission_policy import ExplicitRolePermissionPolicy
from app.services.inventory_summary import (
    AssetLifecycleSummary,
    Availability,
    InventorySummary,
    SummaryMetric,
)

ROOT = Path(__file__).parents[2]


def test_isolated_app_rejects_any_non_restore_check_target(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.integration_application.create_database_engine",
        lambda *_: pytest.fail("Engine creation must follow target and release-gate checks."),
    )
    with pytest.raises(RuntimeError, match="inventory_aios_restore_check"):
        build_isolated_integration_app(
            database_url="postgresql+psycopg://inventory_aios_app@localhost:5432/inventory_aios_dev",
            settings=Settings(
                environment="test",
                frontend_origin="https://restore-check.example.invalid",
                database_url="postgresql+psycopg://inventory_aios_app@localhost:5432/inventory_aios_dev",
            ),
            authentication_configuration=AuthenticationRuntimeConfiguration(),
            authentication_evidence=AuthenticationActivationEvidence(),
            inventory_write_evidence=InventoryWriteActivationEvidence(),
            password_backend=object(),
            dummy_credential=object(),
            canonicalize_username=lambda username: username,
            login_input_policy=object(),
            attempt_hmac_key=b"x" * 32,
            request_limits=object(),
            activity_update_interval_seconds=0,
            clock=lambda: None,
            summary_scope_policy=object(),
            summary_exposure_policy=object(),
            summary_minimum_group_size=1,
        )


def test_isolated_app_still_requires_real_authentication_activation_evidence(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.integration_application.create_database_engine",
        lambda *_: pytest.fail("The app must fail closed before creating an Engine."),
    )
    url = "postgresql+psycopg://inventory_aios_app@localhost:5432/inventory_aios_restore_check"
    config = AuthenticationRuntimeConfiguration(
        enabled=True,
        cookie_name="__Host-inventory-session",
        same_site="strict",
        trusted_origins=("https://restore-check.example.invalid",),
        csrf_signing_key="test-only-key-material-long-enough-for-validation",
        csrf_token_lifetime_seconds=300,
        cookie_max_age_seconds=1800,
        absolute_session_lifetime_seconds=28800,
        inactivity_timeout_seconds=1800,
    )
    with pytest.raises(AuthenticationNotReady):
        build_isolated_integration_app(
            database_url=url,
            settings=Settings(
                environment="test",
                frontend_origin="https://restore-check.example.invalid",
                database_url=url,
            ),
            authentication_configuration=config,
            authentication_evidence=AuthenticationActivationEvidence(),
            inventory_write_evidence=InventoryWriteActivationEvidence(),
            password_backend=object(),
            dummy_credential=object(),
            canonicalize_username=lambda username: username,
            login_input_policy=object(),
            attempt_hmac_key=b"x" * 32,
            request_limits=object(),
            activity_update_interval_seconds=0,
            clock=lambda: None,
            summary_scope_policy=object(),
            summary_exposure_policy=object(),
            summary_minimum_group_size=1,
        )


def test_grant_and_revocation_scripts_are_targeted_additive_and_baseline_preserving():
    grant = (ROOT / "scripts/database/09_operational_runtime_grants.sql").read_text()
    revoke = (ROOT / "scripts/database/10_revoke_operational_runtime_grants.sql").read_text()
    for script in (grant, revoke):
        assert "inventory_aios_restore_check" in script
        assert "inventory_aios_migrator" in script
        assert "d2a8f4c1b790" in script
        assert "BEGIN;" in script and "COMMIT;" in script
    assert "FROM PUBLIC" not in grant
    assert "FROM PUBLIC" not in revoke
    assert "GRANT SELECT, INSERT, UPDATE ON TABLE public.%I TO inventory_aios_app" in grant
    assert "REVOKE SELECT, INSERT, UPDATE ON TABLE" in revoke
    assert "GRANT UPDATE (last_seen_at, revoked_at)" in grant
    assert "REVOKE UPDATE (last_seen_at, revoked_at)" in revoke
    assert "GRANT INSERT (id, actor_user_id" in grant
    assert "REVOKE INSERT (id, actor_user_id" in revoke
    assert "has_column_privilege" in grant and "has_column_privilege" in revoke
    assert "Baseline identity/employee read privileges changed" in revoke
    assert "NOT has_table_privilege('inventory_aios_app','public.users','SELECT')" in grant
    assert "REVOKE SELECT ON TABLE public.users" not in revoke
    assert "REVOKE USAGE ON SCHEMA" not in revoke
    assert "REVOKE CONNECT ON DATABASE" not in revoke


def test_restore_check_integration_guards_match_verified_head():
    for name in (
        "test_auth_postgres_integration.py",
        "test_employee_sync_postgres_integration.py",
        "test_inventory_postgres_integration.py",
        "test_inventory_workflow_postgres_integration.py",
    ):
        source = (ROOT / "backend/tests" / name).read_text()
        assert '"d2a8f4c1b790"' in source
        assert '"b2d4f6a8c013"' not in source
        assert '"c4e2b7a91d60"' not in source


def test_summary_builder_resolves_service_per_request():
    metric = SummaryMetric(status=Availability.AVAILABLE, value=0)
    summary = InventorySummary(
        individual_assets=AssetLifecycleSummary(
            available=metric, allocated=metric, repair=metric, damaged=metric, disposed=metric
        ),
        by_category=[],
        by_location=[],
        quantity_inventory=[],
        availability=Availability.AVAILABLE,
        as_of=None,
    )
    service = Mock()
    service.get.return_value = summary
    service_dependency_calls = Mock()

    def service_dependency():
        service_dependency_calls()
        return service
    principal = Principal(user_id=uuid4(), permissions=frozenset())
    router = build_inventory_summary_router(
        service_dependency=service_dependency,
        principal_dependency=lambda: principal,
    )
    application = FastAPI()
    application.include_router(router)
    with TestClient(application) as client:
        response = client.get("/inventory-summary")
    assert response.status_code == 200
    assert response.json()["availability"] == "available"
    service_dependency_calls.assert_called_once_with()
    service.get.assert_called_once_with(principal)


def test_inventory_admin_scope_rechecks_current_roles_and_rejects_unknown_entities():
    user_id = uuid4()
    session = Mock()
    session.get.return_value = type("User", (), {"id": user_id, "status": "active"})()
    session.scalars.return_value.all.return_value = ["inventory_administrator"]
    scope = OrganizationWideInventoryAdminScopePolicy(
        session=session,
        role_policy=ExplicitRolePermissionPolicy(),
    )

    assert scope.can_access(
        user_id=user_id,
        capability="assets:update",
        entity_type="tracked_asset",
        entity_id=uuid4(),
    )
    assert not scope.can_access(
        user_id=user_id,
        capability="assets:update",
        entity_type="unrecognized_entity",
        entity_id=None,
    )
    session.scalars.return_value.all.return_value = ["security_administrator"]
    assert not scope.can_access(
        user_id=user_id,
        capability="assets:update",
        entity_type="tracked_asset",
        entity_id=uuid4(),
    )
