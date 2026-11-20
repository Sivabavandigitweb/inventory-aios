from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.authentication import (
    InvalidCredential,
    authenticate_principal,
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


def test_missing_credentials_are_rejected() -> None:
    session = MagicMock()
    app.dependency_overrides[get_db_session] = lambda: session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/employees")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
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



