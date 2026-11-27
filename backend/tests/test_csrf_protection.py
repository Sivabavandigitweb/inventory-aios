from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.v1.routes.authentication import (
    HmacDoubleSubmitCsrf,
    TrustedOriginPolicy,
    require_authenticated_csrf,
)


def make_request(headers):
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/auth/login",
            "raw_path": b"/api/v1/auth/login",
            "query_string": b"",
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers],
            "client": ("127.0.0.1", 1234),
            "server": ("inventory.example.invalid", 443),
        }
    )


def make_csrf(now):
    return HmacDoubleSubmitCsrf(
        signing_key=b"fictional-test-key-" * 3,
        auth_cookie_name="__Host-inventory-session",
        max_age_seconds=300,
        clock=lambda: now[0],
        nonce=lambda: b"n" * 32,
    )


def test_signed_login_csrf_requires_matching_cookie_header_and_fresh_signature() -> None:
    now = [datetime(2026, 11, 27, tzinfo=UTC)]
    csrf = make_csrf(now)
    token = csrf.issue_login_token()
    request = make_request(
        [
            ("origin", "https://inventory.example.invalid"),
            ("cookie", f"{csrf.cookie_name}={token}"),
            ("x-csrf-token", token),
        ]
    )
    assert csrf.validate(request, operation="login") is True
    assert csrf.validate(request, operation="logout") is False
    assert csrf.validate(
        make_request([("cookie", f"{csrf.cookie_name}={token}"), ("x-csrf-token", token + "x")]),
        operation="login",
    ) is False
    now[0] += timedelta(minutes=6)
    assert csrf.validate(request, operation="login") is False


def test_logout_csrf_is_bound_to_session_and_rejects_duplicate_csrf_cookies() -> None:
    now = [datetime(2026, 11, 27, tzinfo=UTC)]
    csrf = make_csrf(now)
    session_token = "A" * 43
    other_session_token = "B" * 43
    token = csrf.issue_session_token(session_token)

    def request(auth_token, cookie_header=None):
        cookies = cookie_header or f"{csrf.cookie_name}={token}; __Host-inventory-session={auth_token}"
        return make_request([("cookie", cookies), ("x-csrf-token", token)])

    assert csrf.validate(request(session_token), operation="logout") is True
    assert csrf.validate(request(session_token), operation="authenticated") is True
    assert csrf.validate(request(other_session_token), operation="logout") is False
    assert csrf.validate(request(other_session_token), operation="authenticated") is False
    assert csrf.validate(
        request(session_token, f"{csrf.cookie_name}={token}; {csrf.cookie_name}={token}; __Host-inventory-session={session_token}"),
        operation="logout",
    ) is False


def test_authenticated_state_change_dependency_checks_exact_origin_and_bound_csrf() -> None:
    now = [datetime(2026, 11, 27, tzinfo=UTC)]
    csrf = make_csrf(now)
    session_token = "S" * 43
    token = csrf.issue_session_token(session_token)
    origins = TrustedOriginPolicy(
        allowed_origins=("https://inventory.example.invalid",),
        allow_missing_safe_origin=False,
    )
    app = FastAPI()
    app.post("/mutate", dependencies=[Depends(require_authenticated_csrf(
        origins=origins, csrf=csrf, max_header_bytes=256
    ))])(lambda: {"ok": True})
    client = TestClient(app, base_url="https://inventory.example.invalid")
    headers = {
        "Origin": "https://inventory.example.invalid",
        "X-CSRF-Token": token,
        "Cookie": f"{csrf.cookie_name}={token}; __Host-inventory-session={session_token}",
    }
    assert client.post("/mutate", headers=headers).status_code == 200
    assert client.post("/mutate", headers={**headers, "Origin": "https://evil.invalid"}).status_code == 403
    assert client.post("/mutate", headers={**headers, "X-CSRF-Token": "invalid"}).status_code == 403


def test_csrf_cookie_configuration_requires_host_prefix_and_key_material() -> None:
    try:
        HmacDoubleSubmitCsrf(
            signing_key=b"short",
            auth_cookie_name="__Host-session",
            max_age_seconds=60,
            clock=lambda: datetime.now(UTC),
        )
        assert False, "short CSRF key must be rejected"
    except ValueError:
        pass
