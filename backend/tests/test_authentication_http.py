from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.v1.routes.authentication import (
    AuthCookieConfiguration,
    AuthRequestLimits,
    TrustedOriginPolicy,
    _parse_origin,
    _read_limited_body,
    build_auth_router,
)
from app.core.argon2_passwords import (
    Argon2CostParameters,
    Argon2idPasswordBackend,
    Argon2VerificationLimits,
)
from app.core.credential_verification import (
    CredentialVerificationService,
    DummyVerificationCredential,
    LoginUser,
    PasswordCredentialRecord,
    VerifiedCredential,
)
from app.core.login_orchestration import (
    AuthenticationCompletionDecision,
    LoginAttemptDecision,
    LoginFailureReason,
    LoginInput,
    LoginInputPolicy,
    LoginLogoutOrchestrator,
    LoginRejected,
    LoginResult,
    LoginUnavailable,
    LogoutOutcome,
    LogoutResult,
)
from app.core.password_hashing import PasswordHashingService
from app.core.sessions import (
    ActivityUpdateResult,
    CurrentAccountSessionState,
    IssuedSession,
    NewSessionRecord,
    SessionCreationStateChanged,
    SessionFailureReason,
    SessionLifecycleService,
    SessionPolicy,
    SessionRejected,
    SessionRevocationResult,
    SessionServiceUnavailable,
    StoredSessionRecord,
    ValidatedSession,
)

USER_ID = UUID("10000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
SESSION_TOKEN = secrets.token_urlsafe(32)
ORIGIN = "https://inventory.example"
AUTH_COOKIE = "__Host-inventory_session"
CSRF_COOKIE = "__Host-csrf-test"
CSRF_VALUE = "fictional-test-csrf-value"


class FakeCsrfBoundary:
    """Test-only double-submit fixture; not an operational CSRF implementation."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.failure = False

    def validate(self, request: Request, *, operation: str) -> bool:
        self.calls.append(operation)
        if self.failure:
            raise RuntimeError("private test detail")
        header = request.headers.get("x-csrf-token")
        cookie = request.cookies.get(CSRF_COOKIE)
        return bool(header and cookie and secrets.compare_digest(header, cookie))


class FakeOrchestrator:
    def __init__(self) -> None:
        self.login_failure: Exception | None = None
        self.logout_result = LogoutResult(LogoutOutcome.REVOKED)
        self.login_inputs: list[LoginInput] = []
        self.login_source_keys: list[str | None] = []
        self.logout_tokens: list[str] = []
        self.issued = IssuedSession(
            UUID("30000000-0000-4000-8000-000000000003"),
            USER_ID,
            NOW + timedelta(hours=2),
            SESSION_TOKEN,
        )

    def login(self, payload: LoginInput, *, trusted_source_key: str | None = None) -> LoginResult:
        self.login_inputs.append(payload)
        self.login_source_keys.append(trusted_source_key)
        if self.login_failure:
            raise self.login_failure
        return LoginResult(VerifiedCredential(USER_ID, 5, False), self.issued)

    def logout(self, token: str) -> LogoutResult:
        self.logout_tokens.append(token)
        return self.logout_result


class FakeSessionService:
    def __init__(self) -> None:
        self.failure: Exception | None = None
        self.tokens: list[str] = []
        self.activity_options: list[bool] = []
        self.validated = ValidatedSession(
            UUID("30000000-0000-4000-8000-000000000003"), USER_ID, 5
        )

    def validate(self, token: str, *, update_activity: bool = True) -> ValidatedSession:
        self.tokens.append(token)
        self.activity_options.append(update_activity)
        if self.failure:
            raise self.failure
        return self.validated


class OfflineAccountRepository:
    def __init__(self) -> None:
        self.state = CurrentAccountSessionState(USER_ID, "active", 5)

    def get_current_state(self, user_id: UUID):
        return self.state if user_id == USER_ID else None


class OfflineSessionRepository:
    def __init__(self, accounts: OfflineAccountRepository) -> None:
        self.accounts = accounts
        self.records: dict[bytes, StoredSessionRecord] = {}
        self.fail_create = False

    def create_if_current(self, record: NewSessionRecord) -> None:
        if self.fail_create:
            raise RuntimeError("fictional persistence outage")
        current = self.accounts.get_current_state(record.user_id)
        if (
            current is None
            or current.status != "active"
            or current.credential_version != record.credential_version
        ):
            raise SessionCreationStateChanged
        self.records[record.token_digest] = StoredSessionRecord(
            session_id=record.session_id,
            user_id=record.user_id,
            token_digest=record.token_digest,
            credential_version=record.credential_version,
            created_at=record.created_at,
            last_seen_at=record.last_seen_at,
            expires_at=record.expires_at,
            revoked_at=None,
        )

    def get_by_token_digest(self, token_digest: bytes):
        return self.records.get(token_digest)

    def update_activity_if_current(self, **kwargs):
        for digest, record in tuple(self.records.items()):
            if record.session_id != kwargs["session_id"]:
                continue
            current = self.accounts.get_current_state(record.user_id)
            if (
                record.revoked_at is not None
                or current is None
                or current.status != "active"
                or current.credential_version != kwargs["expected_credential_version"]
                or record.last_seen_at != kwargs["expected_last_seen_at"]
                or kwargs["checked_at"] >= record.expires_at
            ):
                return ActivityUpdateResult.SESSION_INVALID
            self.records[digest] = StoredSessionRecord(
                session_id=record.session_id,
                user_id=record.user_id,
                token_digest=record.token_digest,
                credential_version=record.credential_version,
                created_at=record.created_at,
                last_seen_at=max(record.last_seen_at, kwargs["new_last_seen_at"]),
                expires_at=record.expires_at,
                revoked_at=record.revoked_at,
            )
            return ActivityUpdateResult.UPDATED
        return ActivityUpdateResult.SESSION_INVALID

    def revoke_one_if_active(self, session_id: UUID, revoked_at: datetime):
        for digest, record in tuple(self.records.items()):
            if record.session_id == session_id:
                if record.revoked_at is not None:
                    return SessionRevocationResult.ALREADY_REVOKED
                self.records[digest] = StoredSessionRecord(
                    session_id=record.session_id,
                    user_id=record.user_id,
                    token_digest=record.token_digest,
                    credential_version=record.credential_version,
                    created_at=record.created_at,
                    last_seen_at=record.last_seen_at,
                    expires_at=record.expires_at,
                    revoked_at=revoked_at,
                )
                return SessionRevocationResult.REVOKED
        return SessionRevocationResult.NOT_FOUND

    def revoke_all_for_user(self, user_id: UUID, revoked_at: datetime) -> int:
        return 0


@pytest.fixture
def auth_client():
    orchestration = FakeOrchestrator()
    sessions = FakeSessionService()
    csrf = FakeCsrfBoundary()
    cookie = AuthCookieConfiguration(
        name=AUTH_COOKIE, same_site="lax", max_age_cap_seconds=3600
    )
    origins = TrustedOriginPolicy(
        allowed_origins=(ORIGIN,), allow_missing_safe_origin=True
    )
    limits = AuthRequestLimits(max_body_bytes=256, max_csrf_header_bytes=128)
    input_policy = LoginInputPolicy(
        max_username_characters=80,
        max_password_utf8_bytes=128,
        max_source_key_characters=64,
    )
    application = FastAPI()
    router = build_auth_router(
        orchestration=orchestration,  # type: ignore[arg-type]
        sessions=sessions,  # type: ignore[arg-type]
        cookie=cookie,
        origins=origins,
        csrf=csrf,
        limits=limits,
        input_policy=input_policy,
        clock=lambda: NOW,
    )
    application.include_router(router, prefix="/api/v1")
    with TestClient(application, base_url=ORIGIN) as client:
        client.cookies.set(CSRF_COOKIE, CSRF_VALUE, domain="inventory.example", path="/")
        yield client, orchestration, sessions, csrf


def browser_headers(*, origin: str | None = ORIGIN, csrf: str | None = CSRF_VALUE) -> dict[str, str]:
    headers: dict[str, str] = {}
    if origin is not None:
        headers["Origin"] = origin
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    return headers


def assert_private_response(response) -> None:
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-request-id"]


def test_login_sets_host_only_secure_cookie_and_never_returns_token_json(auth_client) -> None:
    client, orchestration, _, csrf = auth_client

    response = client.post(
        "/api/v1/auth/login",
        headers=browser_headers(),
        json={"username": "fictional.admin", "password": "Fictional password 123"},
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "user_id": str(USER_ID)}
    assert SESSION_TOKEN not in response.text
    assert len(orchestration.login_inputs) == 1
    assert csrf.calls == ["login"]
    cookie_header = response.headers["set-cookie"]
    assert AUTH_COOKIE in cookie_header
    assert "HttpOnly" in cookie_header
    assert "Secure" in cookie_header
    assert "Path=/" in cookie_header
    assert "SameSite=lax" in cookie_header
    assert "Domain=" not in cookie_header
    assert "Max-Age=3600" in cookie_header
    cookie_expires = parsedate_to_datetime(
        next(part.split("=", 1)[1] for part in cookie_header.split(";") if part.strip().startswith("expires="))
    )
    assert cookie_expires <= NOW + timedelta(hours=2)
    assert_private_response(response)


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (
            LoginRejected(LoginFailureReason.CREDENTIALS_REJECTED),
            401,
            "INVALID_CREDENTIALS",
        ),
        (LoginRejected(LoginFailureReason.STALE_IDENTITY), 401, "INVALID_CREDENTIALS"),
        (LoginRejected(LoginFailureReason.ATTEMPT_BLOCKED), 429, "AUTHENTICATION_DENIED"),
        (LoginRejected(LoginFailureReason.AUTHENTICATION_INCOMPLETE), 401, "INVALID_CREDENTIALS"),
        (LoginUnavailable(LoginFailureReason.SESSION_UNAVAILABLE), 503, "AUTHENTICATION_UNAVAILABLE"),
    ],
)
def test_login_failures_are_sanitized_and_never_set_cookie(auth_client, failure, status, code) -> None:
    client, orchestration, _, _ = auth_client
    orchestration.login_failure = failure

    response = client.post(
        "/api/v1/auth/login",
        headers=browser_headers(),
        json={"username": "fictional.admin", "password": "fictional-secret"},
    )

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "fictional-secret" not in response.text
    assert "password" not in response.text.lower()
    assert "set-cookie" not in response.headers
    assert_private_response(response)


def test_unexpected_login_failure_is_sanitized(auth_client) -> None:
    client, orchestration, _, _ = auth_client
    orchestration.login_failure = RuntimeError("sensitive internal detail")
    response = client.post(
        "/api/v1/auth/login",
        headers=browser_headers(),
        json={"username": "fictional.admin", "password": "Fictional password 123"},
    )
    assert response.status_code == 500
    assert "sensitive internal detail" not in response.text
    assert_private_response(response)


def test_login_does_not_emit_malformed_session_token(auth_client) -> None:
    client, orchestration, _, _ = auth_client
    orchestration.issued = IssuedSession(
        UUID("30000000-0000-4000-8000-000000000003"),
        USER_ID,
        NOW + timedelta(hours=1),
        "invalid\r\ntoken",
    )
    response = client.post(
        "/api/v1/auth/login",
        headers=browser_headers(),
        json={"username": "fictional.admin", "password": "Fictional password 123"},
    )
    assert response.status_code == 503
    assert "set-cookie" not in response.headers
    assert "invalid" not in response.text


@pytest.mark.parametrize(
    ("body", "content_type", "status", "secret"),
    [
        (b"{bad", "application/json", 400, ""),
        (b'{"username":"x","password":"SENSITIVE-123"}', "text/plain", 415, ""),
        (
            b'{"username":"x","password":"SENSITIVE-123","extra":"x"}',
            "application/json",
            422,
            "SENSITIVE-123",
        ),
        (b'{"username":"x"}', "application/json", 422, ""),
        (
            b'{"username":"fictional.admin","password":"' + b"x" * 129 + b'"}',
            "application/json",
            422,
            "",
        ),
    ],
)
def test_login_request_validation_is_bounded_and_does_not_echo_values(
    auth_client, body, content_type, status, secret
) -> None:
    client, orchestration, _, _ = auth_client

    response = client.post(
        "/api/v1/auth/login",
        headers={**browser_headers(), "Content-Type": content_type},
        content=body,
    )

    assert response.status_code == status
    if secret:
        assert secret not in response.text
    assert not orchestration.login_inputs
    assert "set-cookie" not in response.headers
    assert_private_response(response)


def test_login_rejects_duplicate_json_keys_without_processing_credentials(auth_client) -> None:
    client, orchestration, _, _ = auth_client
    response = client.post(
        "/api/v1/auth/login",
        headers={**browser_headers(), "Content-Type": "application/json"},
        content=b'{"username":"first","username":"second","password":"FICTIONAL-SECRET"}',
    )
    assert response.status_code == 400
    assert "FICTIONAL-SECRET" not in response.text
    assert not orchestration.login_inputs
    assert "set-cookie" not in response.headers


def test_login_rejects_ambiguous_authentication_cookie(auth_client) -> None:
    client, orchestration, _, _ = auth_client
    response = client.post(
        "/api/v1/auth/login",
        headers={
            **browser_headers(),
            "Cookie": f"{CSRF_COOKIE}={CSRF_VALUE}; {AUTH_COOKIE}=one; {AUTH_COOKIE}=two",
            "Content-Type": "application/json",
        },
        json={"username": "fictional.admin", "password": "Fictional password 123"},
    )
    assert response.status_code == 400
    assert not orchestration.login_inputs
    assert "set-cookie" not in response.headers


def test_login_rejects_oversized_declared_body_before_authentication(auth_client) -> None:
    client, orchestration, _, _ = auth_client
    response = client.post(
        "/api/v1/auth/login",
        headers={
            **browser_headers(),
            "Content-Type": "application/json",
            "Content-Length": "257",
        },
        content=b"{}",
    )
    assert response.status_code == 413
    assert not orchestration.login_inputs


def test_login_rejects_ambiguous_transfer_encoding_and_content_length(auth_client) -> None:
    client, orchestration, _, _ = auth_client
    response = client.post(
        "/api/v1/auth/login",
        headers={
            **browser_headers(),
            "Content-Type": "application/json",
            "Content-Length": "2",
            "Transfer-Encoding": "chunked",
        },
        content=b"{}",
    )
    assert response.status_code == 400
    assert not orchestration.login_inputs


def test_streaming_body_limit_is_checked_independent_of_content_length() -> None:
    # Use an ASGI receive coroutine whose chunks exceed the cap, without a length header.
    from collections import deque

    pieces = deque((b"123456", b"789012"))

    async def streamed_receive():
        if pieces:
            return {"type": "http.request", "body": pieces.popleft(), "more_body": bool(pieces)}
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/login",
            "raw_path": b"/login",
            "query_string": b"",
            "headers": [],
            "server": ("inventory.example", 443),
            "client": ("test", 1),
        },
        streamed_receive,
    )
    import asyncio

    body, failure = asyncio.run(_read_limited_body(request, 10))
    assert body == b""
    assert failure is not None and failure.status_code == 413
    assert "123456" not in failure.body.decode()


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "null",
        "https://evil.example",
        "http://inventory.example",
        "https://inventory.example:444",
        "https://inventory.example.evil",
        "https://inventory.example:invalid",
    ],
)
def test_login_origin_failures_precede_authentication_and_do_not_set_cookie(auth_client, origin) -> None:
    client, orchestration, _, csrf = auth_client
    response = client.post(
        "/api/v1/auth/login",
        headers=browser_headers(origin=origin),
        json={"username": "fictional.admin", "password": "Fictional password 123"},
    )
    assert response.status_code == 403
    assert not orchestration.login_inputs
    assert not csrf.calls
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize("csrf_header", [None, "wrong"])
def test_login_csrf_failure_precedes_authentication(auth_client, csrf_header) -> None:
    client, orchestration, _, csrf = auth_client
    response = client.post(
        "/api/v1/auth/login",
        headers=browser_headers(csrf=csrf_header),
        json={"username": "fictional.admin", "password": "Fictional password 123"},
    )
    assert response.status_code == 403
    assert not orchestration.login_inputs
    assert csrf.calls == (["login"] if csrf_header else [])
    assert "set-cookie" not in response.headers


def test_oversized_csrf_evidence_is_rejected_before_validator_and_login(auth_client) -> None:
    client, orchestration, _, csrf = auth_client
    response = client.post(
        "/api/v1/auth/login",
        headers=browser_headers(csrf="x" * 129),
        json={"username": "fictional.admin", "password": "Fictional password 123"},
    )
    assert response.status_code == 403
    assert not csrf.calls
    assert not orchestration.login_inputs


def test_csrf_protection_outage_fails_closed(auth_client) -> None:
    client, orchestration, _, csrf = auth_client
    csrf.failure = True
    response = client.post(
        "/api/v1/auth/login",
        headers=browser_headers(),
        json={"username": "fictional.admin", "password": "Fictional password 123"},
    )
    assert response.status_code == 503
    assert not orchestration.login_inputs


def test_session_status_reads_only_cookie_and_does_not_extend_activity(auth_client) -> None:
    client, _, sessions, _ = auth_client
    client.cookies.set(AUTH_COOKIE, SESSION_TOKEN, domain="inventory.example", path="/")

    response = client.get("/api/v1/auth/session")

    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "user_id": str(USER_ID)}
    assert sessions.tokens == [SESSION_TOKEN]
    assert sessions.activity_options == [False]
    assert SESSION_TOKEN not in response.text
    assert_private_response(response)


def test_session_status_rejects_query_token_and_missing_cookie(auth_client) -> None:
    client, _, sessions, _ = auth_client
    response = client.get(f"/api/v1/auth/session?token={SESSION_TOKEN}")
    assert response.status_code == 401
    assert not sessions.tokens
    assert SESSION_TOKEN not in response.text


def test_session_status_rejects_duplicate_authentication_cookies(auth_client) -> None:
    client, _, sessions, _ = auth_client
    response = client.get(
        "/api/v1/auth/session",
        headers={"Cookie": f"{AUTH_COOKIE}=one; {AUTH_COOKIE}=two"},
    )
    assert response.status_code == 401
    assert not sessions.tokens
    assert_private_response(response)


@pytest.mark.parametrize(
    ("failure", "status"),
    [
        (SessionRejected(SessionFailureReason.INVALID_TOKEN), 401),
        (SessionRejected(SessionFailureReason.UNKNOWN_SESSION), 401),
        (SessionRejected(SessionFailureReason.REVOKED_SESSION), 401),
        (SessionRejected(SessionFailureReason.ABSOLUTE_EXPIRY), 401),
        (SessionRejected(SessionFailureReason.IDLE_EXPIRY), 401),
        (SessionRejected(SessionFailureReason.INELIGIBLE_ACCOUNT), 401),
        (SessionRejected(SessionFailureReason.CREDENTIAL_MISSING), 401),
        (SessionRejected(SessionFailureReason.CREDENTIAL_VERSION_MISMATCH), 401),
        (SessionServiceUnavailable(SessionFailureReason.REPOSITORY_FAILURE), 503),
    ],
)
def test_session_status_maps_session_and_infrastructure_failures(auth_client, failure, status) -> None:
    client, _, sessions, _ = auth_client
    sessions.failure = failure
    client.cookies.set(AUTH_COOKIE, SESSION_TOKEN, domain="inventory.example", path="/")

    response = client.get("/api/v1/auth/session")
    assert response.status_code == status
    assert SESSION_TOKEN not in response.text
    assert_private_response(response)


def test_logout_revokes_presented_session_and_clears_matching_cookie(auth_client) -> None:
    client, orchestration, _, _ = auth_client
    client.cookies.set(AUTH_COOKIE, SESSION_TOKEN, domain="inventory.example", path="/")

    response = client.post("/api/v1/auth/logout", headers=browser_headers())

    assert response.status_code == 204
    assert orchestration.logout_tokens == [SESSION_TOKEN]
    deletion = response.headers["set-cookie"]
    assert AUTH_COOKIE in deletion
    assert "Max-Age=0" in deletion
    assert "HttpOnly" in deletion and "Secure" in deletion
    assert "Path=/" in deletion and "Domain=" not in deletion
    assert_private_response(response)


@pytest.mark.parametrize(
    "outcome",
    [LogoutOutcome.ALREADY_REVOKED, LogoutOutcome.SESSION_ABSENT, LogoutOutcome.INVALID_TOKEN],
)
def test_logout_is_idempotent_for_nonactive_presented_session(auth_client, outcome) -> None:
    client, orchestration, _, _ = auth_client
    orchestration.logout_result = LogoutResult(outcome)
    client.cookies.set(AUTH_COOKIE, SESSION_TOKEN, domain="inventory.example", path="/")

    response = client.post("/api/v1/auth/logout", headers=browser_headers())

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert orchestration.logout_tokens == [SESSION_TOKEN]


def test_logout_uncertain_clears_cookie_but_reports_failure(auth_client) -> None:
    client, orchestration, _, _ = auth_client
    orchestration.logout_result = LogoutResult(LogoutOutcome.REVOCATION_UNCERTAIN)
    client.cookies.set(AUTH_COOKIE, SESSION_TOKEN, domain="inventory.example", path="/")

    response = client.post("/api/v1/auth/logout", headers=browser_headers())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LOGOUT_UNCERTAIN"
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert_private_response(response)


def test_rejected_logout_has_no_cookie_clearing_side_effect(auth_client) -> None:
    client, orchestration, _, _ = auth_client
    client.cookies.set(AUTH_COOKIE, SESSION_TOKEN, domain="inventory.example", path="/")

    response = client.post(
        "/api/v1/auth/logout",
        headers=browser_headers(origin="https://evil.example", csrf="wrong"),
    )

    assert response.status_code == 403
    assert "set-cookie" not in response.headers
    assert not orchestration.logout_tokens


def test_logout_rejects_duplicate_authentication_cookies_without_side_effect(auth_client) -> None:
    client, orchestration, _, _ = auth_client
    response = client.post(
        "/api/v1/auth/logout",
        headers={
            **browser_headers(),
            "Cookie": f"{CSRF_COOKIE}={CSRF_VALUE}; {AUTH_COOKIE}=one; {AUTH_COOKIE}=two",
        },
    )
    assert response.status_code == 400
    assert "set-cookie" not in response.headers
    assert not orchestration.logout_tokens


@pytest.mark.parametrize(
    ("name", "same_site", "max_age"),
    [
        ("inventory_session", "lax", 30),
        ("__Host-inventory_session", "None", 30),
        ("__Host-inventory_session", "lax", 0),
        ("__Host-inventory_session", "lax", True),
    ],
)
def test_cookie_configuration_rejects_unsafe_or_invalid_values(name, same_site, max_age) -> None:
    with pytest.raises(ValueError):
        AuthCookieConfiguration(
            name=name, same_site=same_site, max_age_cap_seconds=max_age  # type: ignore[arg-type]
        )


def test_explicit_samesite_none_stays_secure_httponly_and_host_only() -> None:
    cookie = AuthCookieConfiguration(
        name=AUTH_COOKIE, same_site="none", max_age_cap_seconds=60
    )
    assert cookie.secure is True
    assert cookie.httponly is True
    assert cookie.path == "/"
    assert cookie.domain is None


def test_security_configuration_objects_are_immutable() -> None:
    cookie = AuthCookieConfiguration(
        name=AUTH_COOKIE, same_site="lax", max_age_cap_seconds=60
    )
    with pytest.raises(AttributeError):
        cookie.same_site = "none"  # type: ignore[misc]
    origins = TrustedOriginPolicy(
        allowed_origins=(ORIGIN,), allow_missing_safe_origin=True
    )
    with pytest.raises(AttributeError):
        origins.allow_missing_safe_origin = False  # type: ignore[misc]
    limits = AuthRequestLimits(max_body_bytes=256, max_csrf_header_bytes=128)
    with pytest.raises(AttributeError):
        limits.max_body_bytes = 1  # type: ignore[misc]


def test_origin_parser_rejects_wildcards_paths_credentials_and_malformed_origins() -> None:
    for value in (
        "*",
        "https://inventory.example/path",
        "https://user:password@inventory.example",
        "null",
        "https://inventory.example:invalid",
        "https://inventory.example:",
        "https://bad_host.example",
        "https://bad..example",
        "https://inventory.example\\evil",
    ):
        assert _parse_origin(value) is None


def test_operational_api_does_not_register_prepared_authentication_router() -> None:
    from app.api.v1.router import api_router

    paths = {
        route.path
        for include in api_router.routes
        for route in include.original_router.routes
    }
    assert "/auth/login" not in paths
    assert "/auth/logout" not in paths
    assert "/auth/session" not in paths


def test_http_login_session_and_logout_compose_real_argon2_and_offline_repositories() -> None:
    password = "Fictional HTTP end-to-end password"
    passwords = PasswordHashingService(
        Argon2idPasswordBackend(
            hash_parameters=Argon2CostParameters(1024, 2, 1, 16, 32),
            verification_limits=Argon2VerificationLimits(4096, 4, 2, 32, 64, 512, 4096),
        )
    )
    encoded = passwords.hash_password(password)
    dummy = passwords.hash_password("Fictional dummy-only password")

    class Users:
        def find_by_canonical_username(self, canonical: str):
            if canonical == "fictional.admin":
                return [LoginUser(USER_ID, "fictional.admin", "active")]
            return []

    accounts = OfflineAccountRepository()

    class Credentials:
        def get_for_user(self, user_id: UUID):
            return PasswordCredentialRecord(
                user_id, encoded, accounts.state.credential_version or 0
            )

    verifier = CredentialVerificationService(
        users=Users(),  # type: ignore[arg-type]
        credentials=Credentials(),  # type: ignore[arg-type]
        passwords=passwords,
        canonicalize_username=str.casefold,
        dummy_credential=DummyVerificationCredential(dummy),
    )
    repository = OfflineSessionRepository(accounts)
    current_time = [NOW]

    def clock():
        return current_time[0]

    lifecycle = SessionLifecycleService(
        sessions=repository,
        accounts=accounts,
        policy=SessionPolicy(
            absolute_lifetime=timedelta(hours=2),
            inactivity_timeout=timedelta(minutes=30),
            activity_update_interval=timedelta(minutes=5),
            maximum_absolute_lifetime=timedelta(days=1),
        ),
        clock=clock,
    )

    class AllowAttempts:
        sources: list[str | None] = []

        def check(self, attempt):
            self.sources.append(attempt.trusted_source_key)
            return LoginAttemptDecision.ALLOW

        def finish_credential_check(self, attempt, outcome):
            return None

    class CompleteTestAuthentication:
        def evaluate(self, verified):
            return AuthenticationCompletionDecision.COMPLETE

    orchestration = LoginLogoutOrchestrator(
        credentials=verifier,
        sessions=lifecycle,
        attempt_protection=AllowAttempts(),
        completion_policy=CompleteTestAuthentication(),
        input_policy=LoginInputPolicy(
            max_username_characters=80,
            max_password_utf8_bytes=128,
            max_source_key_characters=64,
        ),
    )
    csrf = FakeCsrfBoundary()
    application = FastAPI()
    application.include_router(
        build_auth_router(
            orchestration=orchestration,
            sessions=lifecycle,
            cookie=AuthCookieConfiguration(
                name=AUTH_COOKIE, same_site="lax", max_age_cap_seconds=3600
            ),
            origins=TrustedOriginPolicy(
                allowed_origins=(ORIGIN,), allow_missing_safe_origin=True
            ),
            csrf=csrf,
            limits=AuthRequestLimits(max_body_bytes=512, max_csrf_header_bytes=128),
            input_policy=LoginInputPolicy(
                max_username_characters=80,
                max_password_utf8_bytes=128,
                max_source_key_characters=64,
            ),
            clock=clock,
        ),
        prefix="/api/v1",
    )

    with TestClient(application, base_url=ORIGIN) as client:
        client.cookies.set(CSRF_COOKIE, CSRF_VALUE, domain="inventory.example", path="/")
        login = client.post(
            "/api/v1/auth/login",
            headers=browser_headers(),
            json={"username": "FICTIONAL.ADMIN", "password": password},
        )
        assert login.status_code == 200
        assert AllowAttempts.sources[-1] == "testclient"
        assert login.json() == {"authenticated": True, "user_id": str(USER_ID)}
        assert len(repository.records) == 1
        first_token = login.cookies.get(AUTH_COOKIE)
        assert first_token
        session = client.get("/api/v1/auth/session")
        assert session.status_code == 200
        assert session.json() == {"authenticated": True, "user_id": str(USER_ID)}
        first_digest = next(iter(repository.records))
        first_last_seen = repository.records[first_digest].last_seen_at
        current_time[0] += timedelta(minutes=5)
        assert client.get("/api/v1/auth/session").status_code == 200
        assert repository.records[first_digest].last_seen_at == first_last_seen

        second_login = client.post(
            "/api/v1/auth/login",
            headers=browser_headers(),
            json={"username": "fictional.admin", "password": password},
        )
        assert second_login.status_code == 200
        second_token = second_login.cookies.get(AUTH_COOKIE)
        assert second_token and second_token != first_token
        assert len(repository.records) == 2

        client.cookies.set(AUTH_COOKIE, first_token, domain="inventory.example", path="/")
        logout = client.post("/api/v1/auth/logout", headers=browser_headers())
        assert logout.status_code == 204
        assert client.get("/api/v1/auth/session").status_code == 401
        client.cookies.set(AUTH_COOKIE, second_token, domain="inventory.example", path="/")
        assert client.get("/api/v1/auth/session").status_code == 200

        accounts.state = CurrentAccountSessionState(USER_ID, "active", 6)
        assert client.get("/api/v1/auth/session").status_code == 401
        accounts.state = CurrentAccountSessionState(USER_ID, "active", 5)

        third_login = client.post(
            "/api/v1/auth/login",
            headers=browser_headers(),
            json={"username": "fictional.admin", "password": password},
        )
        assert third_login.status_code == 200
        third_token = third_login.cookies.get(AUTH_COOKIE)
        assert third_token
        client.cookies.set(AUTH_COOKIE, third_token, domain="inventory.example", path="/")
        current_time[0] += timedelta(minutes=10)
        assert lifecycle.validate(third_token).user_id == USER_ID
        current_time[0] += timedelta(minutes=30)
        assert client.get("/api/v1/auth/session").status_code == 401

        current_time[0] = NOW
        fourth_login = client.post(
            "/api/v1/auth/login",
            headers=browser_headers(),
            json={"username": "fictional.admin", "password": password},
        )
        assert fourth_login.status_code == 200
        fourth_token = fourth_login.cookies.get(AUTH_COOKIE)
        assert fourth_token
        client.cookies.set(AUTH_COOKIE, fourth_token, domain="inventory.example", path="/")
        current_time[0] += timedelta(hours=2)
        assert client.get("/api/v1/auth/session").status_code == 401

        current_time[0] = NOW
        accounts.state = CurrentAccountSessionState(USER_ID, "active", 5)
        repository.fail_create = True
        failed_login = client.post(
            "/api/v1/auth/login",
            headers=browser_headers(),
            json={"username": "fictional.admin", "password": password},
        )
        assert failed_login.status_code == 503
        assert "set-cookie" not in failed_login.headers

        repository.fail_create = False
        fifth_login = client.post(
            "/api/v1/auth/login",
            headers=browser_headers(),
            json={"username": "fictional.admin", "password": password},
        )
        assert fifth_login.status_code == 200
        fifth_token = fifth_login.cookies.get(AUTH_COOKIE)
        assert fifth_token
        client.cookies.set(AUTH_COOKIE, fifth_token, domain="inventory.example", path="/")
        accounts.state = CurrentAccountSessionState(USER_ID, "inactive", 5)
        assert client.get("/api/v1/auth/session").status_code == 401
