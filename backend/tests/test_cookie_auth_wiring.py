from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.api.v1.authentication_wiring import build_cookie_principal_dependency
from app.core.authentication import DenyAllRolePermissionPolicy
from app.core.errors import AppError
from app.core.sessions import ValidatedSession


def request_with_cookie(cookie: str) -> Request:
    return Request({
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "https", "path": "/protected", "raw_path": b"/protected",
        "query_string": b"", "headers": [(b"cookie", cookie.encode())],
        "client": ("127.0.0.1", 1234), "server": ("inventory.invalid", 443),
    })


def test_cookie_identity_revalidates_session_then_loads_current_deny_all_roles() -> None:
    user_id = uuid4()
    sessions = MagicMock()
    sessions.validate.return_value = ValidatedSession(uuid4(), user_id, 2)
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id=user_id, status="active")
    db.scalars.return_value.all.return_value = ["candidate-admin"]
    dependency = build_cookie_principal_dependency(
        cookie_name="__Host-inventory-session",
        session_service_dependency=lambda: None,
        role_policy_dependency=lambda: None,
        database_session_dependency=lambda: None,
    )
    principal = dependency(
        request_with_cookie("__Host-inventory-session=" + "T" * 43),
        sessions=sessions,
        policy=DenyAllRolePermissionPolicy(),
        session=db,
    )
    assert principal.user_id == user_id
    assert principal.roles == frozenset({"candidate-admin"})
    assert principal.permissions == frozenset()
    sessions.validate.assert_called_once_with("T" * 43, update_activity=True)


@pytest.mark.parametrize("cookie", ["", "__Host-inventory-session=bad token", "__Host-inventory-session=" + "A" * 43 + "; __Host-inventory-session=" + "B" * 43])
def test_cookie_identity_rejects_missing_malformed_and_duplicate_tokens(cookie) -> None:
    sessions = MagicMock()
    dependency = build_cookie_principal_dependency(
        cookie_name="__Host-inventory-session",
        session_service_dependency=lambda: None,
        role_policy_dependency=lambda: None,
        database_session_dependency=lambda: None,
    )
    with pytest.raises(AppError) as error:
        dependency(
            request_with_cookie(cookie), sessions=sessions,
            policy=DenyAllRolePermissionPolicy(), session=MagicMock(),
        )
    assert error.value.status_code == 401
    sessions.validate.assert_not_called()
