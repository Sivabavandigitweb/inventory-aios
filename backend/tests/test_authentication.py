from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError

from app.core.authentication import (
    CredentialProviderUnavailable,
    DenyAllRolePermissionPolicy,
    InvalidCredential,
    RolePermissionPolicyUnavailable,
    authenticate_principal,
    get_credential_verifier,
    get_role_permission_policy,
)
from app.core.authorization import require_employee_reader
from app.core.errors import AppError
from app.db.session import get_db_session
from app.main import app


class FakeVerifier:
    def __init__(self, user_id=None, failure=None):
        self.user_id = user_id or uuid4()
        self.failure = failure

    def verify_access_token(self, token: str):
        if self.failure:
            raise self.failure
        return self.user_id


class FakePolicy:
    def permissions_for(self, role_codes: set[str]) -> frozenset[str]:
        return frozenset()


class StaticPermissionPolicy:
    def __init__(self, permissions: object = frozenset()):
        self.permissions = permissions
        self.role_sets: list[set[str]] = []

    def permissions_for(self, role_codes: set[str]):
        self.role_sets.append(set(role_codes))
        return self.permissions


def active_session(user_id=None) -> MagicMock:
    user_id = user_id or uuid4()
    session = MagicMock()
    session.get.return_value = SimpleNamespace(id=user_id, status="active")
    session.scalars.return_value.all.return_value = []
    return session


def test_missing_credentials_are_rejected() -> None:
    session = MagicMock()
    app.dependency_overrides[get_db_session] = lambda: session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/employees", headers={"X-Request-ID": "test-request-10c"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert response.json()["request_id"] == "test-request-10c"
        assert response.headers["X-Request-ID"] == "test-request-10c"
        session.get.assert_not_called()
        session.scalars.assert_not_called()
    finally:
        app.dependency_overrides.clear()
def test_invalid_credentials_are_rejected_before_user_lookup() -> None:
    session = MagicMock()
    with pytest.raises(AppError) as error:
        authenticate_principal("bad-token", FakeVerifier(failure=InvalidCredential()), session, FakePolicy())
    assert error.value.status_code == 401
    assert error.value.code == "INVALID_CREDENTIALS"
    session.get.assert_not_called()


def test_inactive_user_cannot_authenticate() -> None:
    user_id = uuid4()
    session = MagicMock()
    session.get.return_value = SimpleNamespace(id=user_id, status="inactive")
    with pytest.raises(AppError) as error:
        authenticate_principal("valid-token", FakeVerifier(user_id), session, FakePolicy())
    assert error.value.status_code == 401
    assert error.value.code == "INVALID_CREDENTIALS"
    session.scalars.assert_not_called()


def test_role_without_approved_permission_is_denied() -> None:
    user_id = uuid4()
    session = MagicMock()
    session.get.return_value = SimpleNamespace(id=user_id, status="active")
    session.scalars.return_value.all.return_value = ["inventory_officer"]
    principal = authenticate_principal("valid-token", FakeVerifier(user_id), session, FakePolicy())
    assert principal.roles == frozenset({"inventory_officer"})
    assert principal.permissions == frozenset()
    with pytest.raises(AppError) as error:
        require_employee_reader(principal)
    assert error.value.status_code == 403





def test_expired_credentials_are_rejected_as_unauthorized() -> None:
    session = MagicMock()
    with pytest.raises(AppError) as error:
        authenticate_principal(
            "expired-token", FakeVerifier(failure=InvalidCredential()), session, FakePolicy()
        )
    assert error.value.status_code == 401
    assert error.value.code == "INVALID_CREDENTIALS"
    session.get.assert_not_called()


def test_unconfigured_verifier_returns_safe_service_unavailable() -> None:
    from app.core.authentication import UnconfiguredCredentialVerifier

    with pytest.raises(AppError) as error:
        authenticate_principal(
            "opaque-token", UnconfiguredCredentialVerifier(), MagicMock(), FakePolicy()
        )
    assert (error.value.status_code, error.value.code) == (503, "AUTHENTICATION_UNAVAILABLE")
    assert "token" not in error.value.message.lower()


def test_recognized_verifier_outage_returns_safe_service_unavailable() -> None:
    with pytest.raises(AppError) as error:
        authenticate_principal(
            "opaque-token",
            FakeVerifier(failure=CredentialProviderUnavailable("secret detail")),
            MagicMock(),
            FakePolicy(),
        )
    assert (error.value.status_code, error.value.code) == (503, "AUTHENTICATION_UNAVAILABLE")
    assert "secret" not in error.value.message


@pytest.mark.parametrize("token", ["", " ", "token with spaces", "token\twith-tab"])
def test_malformed_bearer_value_is_rejected_before_verification(token) -> None:
    verifier = MagicMock()
    session = MagicMock()
    with pytest.raises(AppError) as error:
        authenticate_principal(token, verifier, session, FakePolicy())
    assert (error.value.status_code, error.value.code) == (401, "INVALID_CREDENTIALS")
    verifier.verify_access_token.assert_not_called()
    session.get.assert_not_called()


@pytest.mark.parametrize("user_result", [None, object()])
def test_invalid_verifier_identity_result_fails_closed(user_result) -> None:
    verifier = MagicMock()
    verifier.verify_access_token.return_value = user_result
    session = MagicMock()
    with pytest.raises(AppError) as error:
        authenticate_principal("opaque-token", verifier, session, FakePolicy())
    assert (error.value.status_code, error.value.code) == (503, "AUTHENTICATION_UNAVAILABLE")
    session.get.assert_not_called()


def test_database_user_lookup_failure_returns_sanitized_unavailable() -> None:
    session = MagicMock()
    session.get.side_effect = SQLAlchemyError("sensitive SQL details")
    with pytest.raises(AppError) as error:
        authenticate_principal("opaque-token", FakeVerifier(), session, FakePolicy())
    assert (error.value.status_code, error.value.code) == (503, "AUTHENTICATION_UNAVAILABLE")
    assert "sensitive" not in error.value.message
    session.rollback.assert_called_once()


def test_database_role_lookup_failure_returns_sanitized_unavailable() -> None:
    user_id = uuid4()
    session = active_session(user_id)
    session.scalars.side_effect = SQLAlchemyError("sensitive SQL details")
    with pytest.raises(AppError) as error:
        authenticate_principal("opaque-token", FakeVerifier(user_id), session, FakePolicy())
    assert (error.value.status_code, error.value.code) == (503, "AUTHORIZATION_UNAVAILABLE")
    assert "sensitive" not in error.value.message
    session.rollback.assert_called_once()


def test_unmapped_and_inactive_users_share_generic_authentication_failure() -> None:
    verifier = FakeVerifier()
    unmapped = MagicMock()
    unmapped.get.return_value = None
    inactive = MagicMock()
    inactive.get.return_value = SimpleNamespace(id=verifier.user_id, status="inactive")

    responses = []
    for session in (unmapped, inactive):
        with pytest.raises(AppError) as error:
            authenticate_principal("opaque-token", verifier, session, FakePolicy())
        responses.append((error.value.status_code, error.value.code, error.value.message))
    assert responses[0] == responses[1] == (
        401,
        "INVALID_CREDENTIALS",
        "Credentials are invalid or expired.",
    )


def test_inconsistent_local_identity_fails_closed() -> None:
    verifier = FakeVerifier()
    session = MagicMock()
    session.get.return_value = SimpleNamespace(id=uuid4(), status="active")
    with pytest.raises(AppError) as error:
        authenticate_principal("opaque-token", verifier, session, FakePolicy())
    assert (error.value.status_code, error.value.code) == (503, "AUTHENTICATION_UNAVAILABLE")
    session.scalars.assert_not_called()


@pytest.mark.parametrize(
    "permissions",
    [None, {"employees:read:all"}, frozenset({"*"}), frozenset({"employees:*"})],
)
def test_invalid_policy_results_fail_closed(permissions) -> None:
    user_id = uuid4()
    session = active_session(user_id)
    session.scalars.return_value.all.return_value = ["employee_reader"]
    with pytest.raises(AppError) as error:
        authenticate_principal(
            "opaque-token", FakeVerifier(user_id), session, StaticPermissionPolicy(permissions)
        )
    assert (error.value.status_code, error.value.code) == (503, "AUTHORIZATION_UNAVAILABLE")


def test_policy_infrastructure_failure_returns_safe_unavailable() -> None:
    class UnavailablePolicy:
        def permissions_for(self, role_codes: set[str]):
            raise RolePermissionPolicyUnavailable

    user_id = uuid4()
    with pytest.raises(AppError) as error:
        authenticate_principal(
            "opaque-token", FakeVerifier(user_id), active_session(user_id), UnavailablePolicy()
        )
    assert (error.value.status_code, error.value.code) == (503, "AUTHORIZATION_UNAVAILABLE")


def test_policy_database_failure_returns_safe_unavailable() -> None:
    class BrokenDatabasePolicy:
        def permissions_for(self, role_codes: set[str]):
            raise SQLAlchemyError("private authorization store detail")

    user_id = uuid4()
    with pytest.raises(AppError) as error:
        authenticate_principal(
            "opaque-token", FakeVerifier(user_id), active_session(user_id), BrokenDatabasePolicy()
        )
    assert (error.value.status_code, error.value.code) == (503, "AUTHORIZATION_UNAVAILABLE")
    assert "private" not in error.value.message


def test_unexpected_verifier_error_is_sanitized_without_logging_token(caplog) -> None:
    secret = "fictional-token-do-not-log"

    class BrokenVerifier:
        def verify_access_token(self, token: str):
            raise RuntimeError(f"provider failed for {token}")

    with pytest.raises(AppError) as error:
        authenticate_principal(secret, BrokenVerifier(), MagicMock(), FakePolicy())
    assert (error.value.status_code, error.value.code) == (500, "INTERNAL_SERVER_ERROR")
    assert secret not in error.value.message
    assert secret not in caplog.text
    assert "credential_verifier_unexpected_failure" in caplog.text


def test_unexpected_policy_error_uses_generic_internal_error() -> None:
    class BrokenPolicy:
        def permissions_for(self, role_codes: set[str]):
            raise RuntimeError("private policy detail")

    user_id = uuid4()
    with pytest.raises(AppError) as error:
        authenticate_principal(
            "opaque-token", FakeVerifier(user_id), active_session(user_id), BrokenPolicy()
        )
    assert (error.value.status_code, error.value.code) == (500, "INTERNAL_SERVER_ERROR")
    assert "private" not in error.value.message


def test_current_role_assignments_are_reloaded_and_expiry_filter_is_applied() -> None:
    class RoleMappedPolicy:
        def permissions_for(self, role_codes: set[str]) -> frozenset[str]:
            return (
                frozenset({"employees:read:all"})
                if "employee_reader" in role_codes
                else frozenset()
            )

    user_id = uuid4()
    session = active_session(user_id)
    session.scalars.return_value.all.side_effect = [["employee_reader"], []]
    policy = RoleMappedPolicy()
    verifier = FakeVerifier(user_id)

    first = authenticate_principal("opaque-token", verifier, session, policy)
    second = authenticate_principal("opaque-token", verifier, session, policy)

    assert first.permissions == frozenset({"employees:read:all"})
    assert first.roles == frozenset({"employee_reader"})
    assert require_employee_reader(first) is first
    assert second.permissions == frozenset()
    assert second.roles == frozenset()
    with pytest.raises(AppError) as removed_role_error:
        require_employee_reader(second)
    assert removed_role_error.value.status_code == 403
    assert session.scalars.call_count == 2
    compiled = str(session.scalars.call_args_list[0].args[0].compile(dialect=postgresql.dialect()))
    assert "user_roles.valid_from <=" in compiled
    assert "user_roles.valid_to >" in compiled


def test_deny_all_policy_remains_default() -> None:
    assert isinstance(get_role_permission_policy(), DenyAllRolePermissionPolicy)
    assert get_role_permission_policy().permissions_for({"inventory_admin"}) == frozenset()


def test_protected_employee_request_with_no_permission_does_not_query_business_data() -> None:
    user_id = uuid4()
    session = active_session(user_id)
    session.scalars.return_value.all.return_value = ["unapproved_role"]
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_credential_verifier] = lambda: FakeVerifier(user_id)
    app.dependency_overrides[get_role_permission_policy] = lambda: StaticPermissionPolicy(frozenset())
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/employees", headers={"Authorization": "Bearer test-token"})
        assert (response.status_code, response.json()["error"]["code"]) == (403, "FORBIDDEN")
        session.scalar.assert_not_called()
        assert session.scalars.call_count == 1
    finally:
        app.dependency_overrides.clear()


def test_malformed_http_bearer_is_rejected_without_local_user_lookup() -> None:
    session = MagicMock()
    app.dependency_overrides[get_db_session] = lambda: session
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/employees", headers={"Authorization": "Bearer token with spaces"}
            )
        assert (response.status_code, response.json()["error"]["code"]) == (
            401,
            "INVALID_CREDENTIALS",
        )
        session.get.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_unauthorized_employee_registration_does_not_mutate_session() -> None:
    user_id = uuid4()
    session = active_session(user_id)
    session.scalars.return_value.all.return_value = ["unapproved_role"]
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[get_credential_verifier] = lambda: FakeVerifier(user_id)
    app.dependency_overrides[get_role_permission_policy] = lambda: StaticPermissionPolicy(frozenset())
    payload = {
        "employee_number": "TEST-10C-001",
        "first_name": "Fictional",
        "last_name": "Test",
        "department_id": str(uuid4()),
        "team_id": str(uuid4()),
        "designation_id": str(uuid4()),
        "joining_date": "2026-01-01",
    }
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/employees", json=payload, headers={"Authorization": "Bearer test-token"}
            )
        assert (response.status_code, response.json()["error"]["code"]) == (403, "FORBIDDEN")
        session.add.assert_not_called()
        session.commit.assert_not_called()
        session.scalar.assert_not_called()
    finally:
        app.dependency_overrides.clear()
