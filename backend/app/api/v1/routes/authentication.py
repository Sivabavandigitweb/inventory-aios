"""Isolated browser-authentication HTTP adapter; deliberately not included by api.router."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Literal, Protocol
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError
from starlette.concurrency import run_in_threadpool

from app.core.login_orchestration import (
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
from app.core.sessions import (
    SessionLifecycleService,
    SessionRejected,
    SessionServiceUnavailable,
    ValidatedSession,
)


class AuthCookieConfiguration:
    """Explicit secure host-only cookie settings; never choose deployment defaults here."""

    __slots__ = ("name", "same_site", "max_age_cap_seconds")

    def __init__(
        self,
        *,
        name: str,
        same_site: Literal["strict", "lax", "none"],
        max_age_cap_seconds: int,
    ) -> None:
        if not isinstance(name, str) or not name.startswith("__Host-"):
            raise ValueError("Authentication cookie must use a __Host- name.")
        suffix = name.removeprefix("__Host-")
        if (
            not suffix
            or len(name) > 128
            or any(
                not char.isascii()
                or not (char.isalnum() or char in "!#$%&'*+-.^_`|~")
                for char in suffix
            )
        ):
            raise ValueError("Authentication cookie name is invalid.")
        if same_site not in ("strict", "lax", "none"):
            raise ValueError("SameSite must be explicitly configured.")
        if type(max_age_cap_seconds) is not int or max_age_cap_seconds <= 0:
            raise ValueError("Cookie maximum age must be a positive integer.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "same_site", same_site)
        object.__setattr__(self, "max_age_cap_seconds", max_age_cap_seconds)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Cookie configuration is immutable.")

    @property
    def secure(self) -> bool:
        return True

    @property
    def httponly(self) -> bool:
        return True

    @property
    def path(self) -> str:
        return "/"

    @property
    def domain(self) -> None:
        return None


class TrustedOriginPolicy:
    """Exact scheme/host/effective-port allowlist; no proxy headers or wildcard support."""

    __slots__ = ("_origins", "allow_missing_safe_origin")

    def __init__(
        self, *, allowed_origins: tuple[str, ...], allow_missing_safe_origin: bool
    ) -> None:
        if not allowed_origins:
            raise ValueError("At least one trusted origin is required.")
        normalized: set[tuple[str, str, int]] = set()
        for origin in allowed_origins:
            parsed = _parse_origin(origin)
            if parsed is None:
                raise ValueError("Trusted origins must be exact HTTP(S) origins.")
            normalized.add(parsed)
        if type(allow_missing_safe_origin) is not bool:
            raise ValueError("Missing-origin policy must be explicit.")
        object.__setattr__(self, "_origins", frozenset(normalized))
        object.__setattr__(self, "allow_missing_safe_origin", allow_missing_safe_origin)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Origin policy is immutable.")

    def allows(self, request: Request, *, safe_method: bool) -> bool:
        values = request.headers.getlist("origin")
        if len(values) == 0:
            return safe_method and self.allow_missing_safe_origin
        if len(values) != 1:
            return False
        supplied = values[0]
        if supplied == "null":
            return False
        parsed = _parse_origin(supplied)
        return parsed is not None and parsed in self._origins

    def matches_configuration(self, origins: tuple[str, ...]) -> bool:
        parsed = tuple(_parse_origin(origin) for origin in origins)
        return bool(parsed) and all(origin is not None for origin in parsed) and frozenset(parsed) == self._origins

    @property
    def allows_missing_safe_origin(self) -> bool:
        return self.allow_missing_safe_origin


class CsrfValidator(Protocol):
    """Trusted server-side CSRF boundary; the adapter never accepts a boolean from input."""

    def validate(
        self, request: Request, *, operation: Literal["login", "logout", "authenticated"]
    ) -> bool: ...


class HmacDoubleSubmitCsrf:
    """Signed double-submit tokens; logout tokens are bound to the auth session.

    The key, exact trusted origins, cookie policy, and same-origin deployment remain
    explicit configuration. This class is not activated by the operational app.
    """

    __slots__ = ("_key", "_auth_cookie", "cookie_name", "_max_age", "_clock", "_nonce")

    def __init__(
        self,
        *,
        signing_key: bytes,
        auth_cookie_name: str,
        cookie_name: str = "__Host-inventory-csrf",
        max_age_seconds: int,
        clock: Callable[[], datetime],
        nonce: Callable[[], bytes] = lambda: secrets.token_bytes(32),
    ) -> None:
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("CSRF signing key must contain at least 32 bytes.")
        if not auth_cookie_name.startswith("__Host-") or not cookie_name.startswith("__Host-"):
            raise ValueError("CSRF and authentication cookies must be host-only __Host- cookies.")
        if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 3600:
            raise ValueError("CSRF token lifetime is outside the safe configured range.")
        self._key = bytes(signing_key)
        self._auth_cookie = auth_cookie_name
        self.cookie_name = cookie_name
        self._max_age = max_age_seconds
        self._clock = clock
        self._nonce = nonce

    def issue_login_token(self) -> str:
        return self._issue("login", b"")

    def issue_session_token(self, session_token: str) -> str:
        binding = _csrf_session_binding(session_token)
        return self._issue("authenticated", binding)

    def matches_configuration(self, *, signing_key: bytes, auth_cookie_name: str, lifetime: int) -> bool:
        return (
            hmac.compare_digest(self._key, signing_key)
            and self._auth_cookie == auth_cookie_name
            and self._max_age == lifetime
        )

    def validate(
        self, request: Request, *, operation: Literal["login", "logout", "authenticated"]
    ) -> bool:
        header_values = request.headers.getlist("x-csrf-token")
        cookie_token, malformed = _extract_unique_cookie(request, self.cookie_name)
        if malformed or len(header_values) != 1 or not cookie_token:
            return False
        header = header_values[0]
        if len(header) > 256 or not hmac.compare_digest(header, cookie_token):
            return False
        pieces = header.split(".")
        if len(pieces) != 4 or pieces[0] != "v1":
            return False
        _, timestamp, nonce, supplied_mac = pieces
        if not (timestamp.isascii() and timestamp.isdigit() and 1 <= len(timestamp) <= 12):
            return False
        if not (8 <= len(nonce) <= 64 and all(ch.isalnum() or ch in "_-" for ch in nonce)):
            return False
        try:
            token_time = int(timestamp)
            now = int(_as_utc(self._clock()).timestamp())
        except Exception:
            return False
        if token_time > now + 30 or now - token_time > self._max_age:
            return False
        binding = b""
        signed_operation = operation
        if operation in ("logout", "authenticated"):
            session_token, bad_cookie = _extract_unique_cookie(request, self._auth_cookie)
            if bad_cookie or not session_token:
                return False
            try:
                binding = _csrf_session_binding(session_token)
            except ValueError:
                return False
            signed_operation = "authenticated"
        elif operation != "login":
            return False
        expected = self._mac(signed_operation, token_time, nonce, binding)
        return hmac.compare_digest(supplied_mac, expected)

    @property
    def max_age_seconds(self) -> int:
        return self._max_age

    def _issue(self, operation: str, binding: bytes) -> str:
        try:
            now = _as_utc(self._clock())
            nonce = self._nonce()
        except Exception:
            raise RuntimeError("CSRF token service is unavailable.") from None
        if now is None or not isinstance(nonce, bytes) or not 16 <= len(nonce) <= 48:
            raise RuntimeError("CSRF token service is unavailable.")
        encoded_nonce = base64.urlsafe_b64encode(nonce).rstrip(b"=").decode("ascii")
        timestamp = int(now.timestamp())
        signature = self._mac(operation, timestamp, encoded_nonce, binding)
        return f"v1.{timestamp}.{encoded_nonce}.{signature}"

    def _mac(self, operation: str, timestamp: int, nonce: str, binding: bytes) -> str:
        message = b"|".join(
            (b"inventory-aios-csrf-v1", operation.encode(), str(timestamp).encode(), nonce.encode(), binding)
        )
        return base64.urlsafe_b64encode(hmac.new(self._key, message, hashlib.sha256).digest()).rstrip(b"=").decode("ascii")


def _csrf_session_binding(session_token: str) -> bytes:
    if (
        not isinstance(session_token, str)
        or len(session_token) != 43
        or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for char in session_token)
    ):
        raise ValueError("Invalid session token.")
    return hashlib.sha256(session_token.encode("ascii")).digest()


class AuthRequestLimits:
    __slots__ = ("max_body_bytes", "max_csrf_header_bytes")

    def __init__(self, *, max_body_bytes: int, max_csrf_header_bytes: int) -> None:
        if any(
            type(value) is not int or value <= 0
            for value in (max_body_bytes, max_csrf_header_bytes)
        ):
            raise ValueError("Authentication request limits must be positive integers.")
        object.__setattr__(self, "max_body_bytes", max_body_bytes)
        object.__setattr__(self, "max_csrf_header_bytes", max_csrf_header_bytes)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Request limits are immutable.")


def require_authenticated_csrf(
    *, origins: TrustedOriginPolicy, csrf: CsrfValidator, max_header_bytes: int
):
    """Return a fail-closed dependency for cookie-authenticated state changes.

    Apply it alongside normal session authentication, capability, resource-scope,
    and business-rule dependencies on each future mutating endpoint.
    """
    if type(max_header_bytes) is not int or max_header_bytes <= 0:
        raise ValueError("CSRF header limit must be a positive integer.")

    async def dependency(request: Request) -> None:
        if not origins.allows(request, safe_method=False):
            raise HTTPException(status_code=403, detail="Request origin is not allowed.")
        values = request.headers.getlist("x-csrf-token")
        if (
            len(values) != 1
            or not values[0]
            or len(values[0].encode("utf-8")) > max_header_bytes
        ):
            raise HTTPException(status_code=403, detail="Request security validation failed.")
        try:
            valid = await run_in_threadpool(
                csrf.validate, request, operation="authenticated"
            )
        except Exception:
            raise HTTPException(
                status_code=503, detail="Request security validation is unavailable."
            ) from None
        if valid is not True:
            raise HTTPException(status_code=403, detail="Request security validation failed.")

    return dependency


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    username: StrictStr
    password: StrictStr


@dataclass(frozen=True, slots=True)
class AuthRouteServices:
    orchestration: LoginLogoutOrchestrator
    sessions: SessionLifecycleService


class _DuplicateJsonKey(ValueError):
    pass


def build_auth_router(
    *,
    orchestration: LoginLogoutOrchestrator | None,
    sessions: SessionLifecycleService | None,
    services_dependency: Callable[..., AuthRouteServices] | None = None,
    cookie: AuthCookieConfiguration,
    origins: TrustedOriginPolicy,
    csrf: CsrfValidator,
    limits: AuthRequestLimits,
    input_policy: LoginInputPolicy,
    clock: Callable[[], datetime],
) -> APIRouter:
    """Build a router only when every security dependency is explicitly provided.

    The operational API router intentionally does not import or include this router.
    """

    router = APIRouter(prefix="/auth", tags=["authentication-preview"])

    if services_dependency is None:
        if orchestration is None or sessions is None:
            raise ValueError("Authentication router services must be explicitly provided.")

        def get_services() -> AuthRouteServices:
            return AuthRouteServices(orchestration, sessions)

        services_dependency = get_services

    @router.post("/login")
    async def login(request: Request, services: AuthRouteServices = Depends(services_dependency)) -> Response:
        rejection = await _check_browser_request(
            request, origins=origins, csrf=csrf, operation="login", limits=limits
        )
        if rejection is not None:
            return rejection
        if _extract_unique_cookie(request, cookie.name)[1]:
            return _error(request, 400, "INVALID_REQUEST", "The request is invalid.")

        content_type = request.headers.getlist("content-type")
        if len(content_type) != 1 or content_type[0].split(";", 1)[0].strip().lower() != "application/json":
            return _error(request, 415, "UNSUPPORTED_MEDIA_TYPE", "A JSON request is required.")

        body, failure = await _read_limited_body(request, limits.max_body_bytes)
        if failure is not None:
            return failure
        try:
            decoded = json.loads(body, object_pairs_hook=_reject_duplicate_json_keys)
        except (json.JSONDecodeError, UnicodeDecodeError, _DuplicateJsonKey):
            return _error(request, 400, "INVALID_REQUEST", "The request body is invalid.")
        try:
            payload = LoginRequest.model_validate(decoded)
        except ValidationError:
            # Never include Pydantic input/value details: these contain the password.
            return _error(request, 422, "INVALID_REQUEST", "The request fields are invalid.")
        if not input_policy.accepts(payload.username, payload.password):
            return _error(request, 422, "INVALID_REQUEST", "The request fields are invalid.")

        try:
            _preflight_now = _as_utc(clock())
            if _preflight_now is None:
                return _error(request, 503, "AUTHENTICATION_UNAVAILABLE", _UNAVAILABLE)
        except Exception:
            return _error(request, 503, "AUTHENTICATION_UNAVAILABLE", _UNAVAILABLE)
        try:
            result = await run_in_threadpool(
                services.orchestration.login,
                LoginInput(payload.username, payload.password),
                trusted_source_key=request.client.host if request.client is not None else None,
            )
        except LoginRejected as error:
            if error.reason is LoginFailureReason.INVALID_INPUT:
                return _error(request, 422, "INVALID_REQUEST", "The request fields are invalid.")
            if error.reason is LoginFailureReason.ATTEMPT_BLOCKED:
                return _error(request, 429, "AUTHENTICATION_DENIED", _DENIED)
            return _error(request, 401, "INVALID_CREDENTIALS", _INVALID_CREDENTIALS)
        except LoginUnavailable:
            return _error(request, 503, "AUTHENTICATION_UNAVAILABLE", _UNAVAILABLE)
        except Exception:
            return _error(request, 500, "INTERNAL_SERVER_ERROR", _INTERNAL_ERROR)

        try:
            if (
                not isinstance(result, LoginResult)
                or not isinstance(result.user_id, UUID)
                or type(result.credential_version) is not int
                or result.credential_version <= 0
            ):
                return _error(request, 503, "AUTHENTICATION_UNAVAILABLE", _UNAVAILABLE)
            # Compute Max-Age from response-time so it cannot outlast server expiry.
            response_time = _as_utc(clock())
            expiry = _as_utc(result.expires_at)
            if response_time is None or expiry is None or expiry <= response_time:
                return _error(request, 503, "AUTHENTICATION_UNAVAILABLE", _UNAVAILABLE)
            cookie_expiry = min(
                expiry,
                response_time + timedelta(seconds=cookie.max_age_cap_seconds),
            )
            max_age = int((cookie_expiry - response_time).total_seconds())
            if max_age <= 0:
                return _error(request, 503, "AUTHENTICATION_UNAVAILABLE", _UNAVAILABLE)
            issued = result.session_for_cookie_delivery()
            if issued.user_id != result.user_id:
                return _error(request, 503, "AUTHENTICATION_UNAVAILABLE", _UNAVAILABLE)
            token = issued.token_for_cookie_delivery()
            if (
                not isinstance(token, str)
                or len(token) != 43
                or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-" for char in token)
            ):
                return _error(request, 503, "AUTHENTICATION_UNAVAILABLE", _UNAVAILABLE)
        except Exception:
            return _error(request, 503, "AUTHENTICATION_UNAVAILABLE", _UNAVAILABLE)

        response_payload: dict[str, object] = {
            "authenticated": True,
            "user_id": str(result.user_id),
        }
        csrf_token = None
        if isinstance(csrf, HmacDoubleSubmitCsrf):
            try:
                csrf_token = csrf.issue_session_token(token)
                response_payload["csrf_token"] = csrf_token
            except Exception:
                return _error(request, 503, "BROWSER_SECURITY_UNAVAILABLE", _UNAVAILABLE)
        response = _json_response(request, 200, response_payload)
        try:
            response.set_cookie(
                key=cookie.name,
                value=token,
                max_age=max_age,
                expires=cookie_expiry,
                path=cookie.path,
                domain=None,
                secure=True,
                httponly=True,
                samesite=cookie.same_site,
            )
        except Exception:
            return _error(request, 503, "AUTHENTICATION_UNAVAILABLE", _UNAVAILABLE)
        if csrf_token is not None:
            csrf_expiry = min(cookie_expiry, response_time + timedelta(seconds=csrf.max_age_seconds))
            _set_csrf_cookie(response, csrf, cookie, csrf_token, csrf_expiry, response_time)
        return response

    @router.get("/csrf")
    async def login_csrf_token(request: Request) -> Response:
        if not origins.allows(request, safe_method=True):
            return _error(request, 403, "ORIGIN_REJECTED", _DENIED)
        if not isinstance(csrf, HmacDoubleSubmitCsrf):
            return _error(request, 503, "BROWSER_SECURITY_UNAVAILABLE", _UNAVAILABLE)
        try:
            token = csrf.issue_login_token()
            now = _as_utc(clock())
            if now is None:
                raise ValueError
            expiry = now + timedelta(seconds=min(cookie.max_age_cap_seconds, csrf.max_age_seconds))
            response = _json_response(request, 200, {"csrf_token": token})
            _set_csrf_cookie(response, csrf, cookie, token, expiry, now)
            return response
        except Exception:
            return _error(request, 503, "BROWSER_SECURITY_UNAVAILABLE", _UNAVAILABLE)

    @router.get("/session")
    async def session_status(request: Request, services: AuthRouteServices = Depends(services_dependency)) -> Response:
        if not origins.allows(request, safe_method=True):
            return _error(request, 403, "ORIGIN_REJECTED", _DENIED)
        token, malformed_cookie = _extract_unique_cookie(request, cookie.name)
        if malformed_cookie:
            return _error(request, 401, "INVALID_SESSION", _INVALID_SESSION)
        if not token:
            return _error(request, 401, "INVALID_SESSION", _INVALID_SESSION)
        try:
            validated = await run_in_threadpool(
                services.sessions.validate, token, update_activity=False
            )
        except SessionRejected:
            return _error(request, 401, "INVALID_SESSION", _INVALID_SESSION)
        except SessionServiceUnavailable:
            return _error(request, 503, "AUTHENTICATION_UNAVAILABLE", _UNAVAILABLE)
        except Exception:
            return _error(request, 500, "INTERNAL_SERVER_ERROR", _INTERNAL_ERROR)
        if (
            not isinstance(validated, ValidatedSession)
            or not isinstance(validated.user_id, UUID)
            or type(validated.credential_version) is not int
            or validated.credential_version <= 0
        ):
            return _error(request, 503, "AUTHENTICATION_UNAVAILABLE", _UNAVAILABLE)
        response_payload: dict[str, object] = {
            "authenticated": True,
            "user_id": str(validated.user_id),
        }
        if isinstance(csrf, HmacDoubleSubmitCsrf):
            try:
                session_csrf = csrf.issue_session_token(token)
                response_payload["csrf_token"] = session_csrf
                response = _json_response(request, 200, response_payload)
                current_time = _as_utc(clock())
                if current_time is None:
                    return _error(request, 503, "AUTHENTICATION_UNAVAILABLE", _UNAVAILABLE)
                expiry = current_time + timedelta(
                    seconds=min(cookie.max_age_cap_seconds, csrf.max_age_seconds)
                )
                _set_csrf_cookie(response, csrf, cookie, session_csrf, expiry, current_time)
                return response
            except Exception:
                return _error(request, 503, "BROWSER_SECURITY_UNAVAILABLE", _UNAVAILABLE)
        return _json_response(request, 200, response_payload)

    @router.post("/logout")
    async def logout(request: Request, services: AuthRouteServices = Depends(services_dependency)) -> Response:
        rejection = await _check_browser_request(
            request, origins=origins, csrf=csrf, operation="logout", limits=limits
        )
        if rejection is not None:
            return rejection

        token, malformed_cookie = _extract_unique_cookie(request, cookie.name)
        if malformed_cookie:
            return _error(request, 400, "INVALID_REQUEST", "The request is invalid.")
        try:
            result = await run_in_threadpool(services.orchestration.logout, token or "")
        except Exception:
            result = None

        uncertain = (
            not isinstance(result, LogoutResult)
            or result.outcome is LogoutOutcome.REVOCATION_UNCERTAIN
        )
        response = (
            _error(request, 503, "LOGOUT_UNCERTAIN", _UNAVAILABLE)
            if uncertain
            else Response(status_code=204)
        )
        _apply_response_headers(request, response)
        response.delete_cookie(
            key=cookie.name,
            path=cookie.path,
            domain=None,
            secure=True,
            httponly=True,
            samesite=cookie.same_site,
        )
        if isinstance(csrf, HmacDoubleSubmitCsrf):
            response.delete_cookie(
                key=csrf.cookie_name,
                path="/",
                domain=None,
                secure=True,
                httponly=True,
                samesite=cookie.same_site,
            )
        return response

    return router


async def _check_browser_request(
    request: Request,
    *,
    origins: TrustedOriginPolicy,
    csrf: CsrfValidator,
    operation: Literal["login", "logout"],
    limits: AuthRequestLimits,
) -> Response | None:
    if not origins.allows(request, safe_method=False):
        return _error(request, 403, "ORIGIN_REJECTED", _DENIED)
    csrf_headers = request.headers.getlist("x-csrf-token")
    if (
        len(csrf_headers) != 1
        or not csrf_headers[0]
        or len(csrf_headers[0].encode("utf-8")) > limits.max_csrf_header_bytes
    ):
        return _error(request, 403, "CSRF_REJECTED", _DENIED)
    try:
        valid = await run_in_threadpool(csrf.validate, request, operation=operation)
    except Exception:
        return _error(request, 503, "BROWSER_SECURITY_UNAVAILABLE", _UNAVAILABLE)
    if valid is not True:
        return _error(request, 403, "CSRF_REJECTED", _DENIED)
    return None


async def _read_limited_body(
    request: Request, max_bytes: int
) -> tuple[bytes, Response | None]:
    content_lengths = request.headers.getlist("content-length")
    transfer_encodings = request.headers.getlist("transfer-encoding")
    if content_lengths and transfer_encodings:
        return b"", _error(request, 400, "INVALID_REQUEST", "The request body is invalid.")
    if len(content_lengths) > 1:
        return b"", _error(request, 400, "INVALID_REQUEST", "The request body is invalid.")
    if content_lengths:
        try:
            declared_length = int(content_lengths[0])
        except ValueError:
            return b"", _error(request, 400, "INVALID_REQUEST", "The request body is invalid.")
        if declared_length < 0:
            return b"", _error(request, 400, "INVALID_REQUEST", "The request body is invalid.")
        if declared_length > max_bytes:
            return b"", _error(request, 413, "REQUEST_TOO_LARGE", "The request is too large.")
    collected = bytearray()
    try:
        async for chunk in request.stream():
            if len(collected) + len(chunk) > max_bytes:
                return b"", _error(request, 413, "REQUEST_TOO_LARGE", "The request is too large.")
            collected.extend(chunk)
    except Exception:
        return b"", _error(request, 400, "INVALID_REQUEST", "The request body is invalid.")
    return bytes(collected), None


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey
        result[key] = value
    return result


def _extract_unique_cookie(request: Request, name: str) -> tuple[str | None, bool]:
    """Return one exact cookie value; duplicate/malformed target cookies fail closed."""
    matches: list[str] = []
    for header in request.headers.getlist("cookie"):
        for part in header.split(";"):
            item = part.strip()
            key, separator, value = item.partition("=")
            if key == name:
                if not separator or not value or any(ord(char) < 33 or ord(char) > 126 for char in value):
                    return None, True
                matches.append(value)
    if len(matches) > 1:
        return None, True
    return (matches[0] if matches else None), False


def _parse_origin(value: str) -> tuple[str, str, int] | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    if any(char.isspace() or ord(char) < 32 for char in value) or "*" in value:
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme.lower() not in ("http", "https")
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.hostname is None
            or parsed.netloc.endswith(":")
            or "\\" in parsed.netloc
        ):
            return None
        scheme = parsed.scheme.lower()
        host = parsed.hostname.encode("idna").decode("ascii").lower()
        try:
            host = ipaddress.ip_address(host).compressed.lower()
        except ValueError:
            labels_host = host[:-1] if host.endswith(".") else host
            labels = labels_host.split(".")
            if (
                len(host) > 253
                or not labels_host
                or any(
                    not label
                    or len(label) > 63
                    or not label[0].isalnum()
                    or not label[-1].isalnum()
                    or any(not (char.isascii() and (char.isalnum() or char == "-")) for char in label)
                    for label in labels
                )
            ):
                return None
        explicit_port = parsed.port
        port = explicit_port if explicit_port is not None else (443 if scheme == "https" else 80)
        if not 1 <= port <= 65535:
            return None
        return scheme, host, port
    except (UnicodeError, ValueError):
        return None


def _as_utc(value: object) -> datetime | None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError):
        return None


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    if (
        isinstance(value, str)
        and 0 < len(value) <= 128
        and all(32 <= ord(char) < 127 for char in value)
    ):
        return value
    return str(uuid4())


def _apply_response_headers(request: Request, response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Request-ID"] = _request_id(request)


def _set_csrf_cookie(
    response: Response,
    csrf: HmacDoubleSubmitCsrf,
    auth_cookie: AuthCookieConfiguration,
    token: str,
    expires_at: datetime,
    now: datetime,
) -> None:
    max_age = int((expires_at - now).total_seconds())
    if max_age <= 0 or max_age > min(auth_cookie.max_age_cap_seconds, csrf.max_age_seconds):
        raise ValueError("CSRF cookie lifetime is invalid.")
    response.set_cookie(
        key=csrf.cookie_name,
        value=token,
        max_age=max_age,
        expires=expires_at,
        path="/",
        domain=None,
        secure=True,
        httponly=True,
        samesite=auth_cookie.same_site,
    )
def _json_response(request: Request, status_code: int, payload: dict[str, object]) -> JSONResponse:
    response = JSONResponse(status_code=status_code, content=payload)
    _apply_response_headers(request, response)
    return response


def _error(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    return _json_response(
        request,
        status_code,
        {"error": {"code": code, "message": message}, "request_id": _request_id(request)},
    )


_INVALID_CREDENTIALS = "Credentials are invalid or expired."
_INVALID_SESSION = "The session is invalid or expired."
_DENIED = "The request could not be authenticated."
_UNAVAILABLE = "Authentication is temporarily unavailable."
_INTERNAL_ERROR = "An unexpected error occurred."
