"""Offline login/logout composition over credential and session services."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.core.credential_verification import (
    CredentialRejected,
    CredentialVerificationService,
    CredentialVerificationUnavailable,
    VerifiedCredential,
)
from app.core.sessions import (
    IssuedSession,
    SessionFailureReason,
    SessionLifecycleService,
    SessionRejected,
    SessionRevocationResult,
    SessionServiceUnavailable,
)


class LoginFailureReason(StrEnum):
    INVALID_INPUT = "invalid_input"
    ATTEMPT_BLOCKED = "attempt_blocked"
    CREDENTIALS_REJECTED = "credentials_rejected"
    AUTHENTICATION_INCOMPLETE = "authentication_incomplete"
    AUTHENTICATION_DENIED = "authentication_denied"
    STALE_IDENTITY = "stale_identity"
    PROTECTION_UNAVAILABLE = "protection_unavailable"
    CREDENTIAL_VERIFICATION_UNAVAILABLE = "credential_verification_unavailable"
    COMPLETION_POLICY_UNAVAILABLE = "completion_policy_unavailable"
    SESSION_UNAVAILABLE = "session_unavailable"
    UNEXPECTED_FAILURE = "unexpected_failure"


class LoginRejected(Exception):
    """Generic denial for invalid credentials or unmet authentication conditions."""

    public_message = "Login could not be completed."

    def __init__(self, reason: LoginFailureReason) -> None:
        self.reason = reason
        super().__init__(self.public_message)


class LoginUnavailable(Exception):
    """Sanitized login infrastructure/policy failure."""

    public_message = "Login service is temporarily unavailable."

    def __init__(self, reason: LoginFailureReason) -> None:
        self.reason = reason
        super().__init__(self.public_message)


class LoginInputPolicy:
    """Explicit input bounds; constructor values are not operational defaults."""

    __slots__ = (
        "max_username_characters",
        "max_password_utf8_bytes",
        "max_source_key_characters",
    )

    def __init__(
        self,
        *,
        max_username_characters: int,
        max_password_utf8_bytes: int,
        max_source_key_characters: int,
    ) -> None:
        limits = (
            max_username_characters,
            max_password_utf8_bytes,
            max_source_key_characters,
        )
        if any(type(value) is not int or value <= 0 for value in limits):
            raise ValueError("Login input limits must be positive integers.")
        self.max_username_characters = max_username_characters
        self.max_password_utf8_bytes = max_password_utf8_bytes
        self.max_source_key_characters = max_source_key_characters

    def accepts(self, username: object, password: object) -> bool:
        if not isinstance(username, str) or not username:
            return False
        if len(username) > self.max_username_characters:
            return False
        if not isinstance(password, str) or not password:
            return False
        try:
            return len(password.encode("utf-8")) <= self.max_password_utf8_bytes
        except UnicodeEncodeError:
            return False

    def accepts_source_key(self, source_key: object) -> bool:
        return source_key is None or (
            isinstance(source_key, str)
            and bool(source_key)
            and len(source_key) <= self.max_source_key_characters
        )


class LoginInput:
    """Short-lived, bounded-at-use credentials; representations/serialization redact them."""

    __slots__ = ("__username", "__password")

    def __init__(self, username: str, password: str) -> None:
        object.__setattr__(self, "_LoginInput__username", username)
        object.__setattr__(self, "_LoginInput__password", password)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Login input is immutable.")

    def _username_for_internal_use(self) -> str:
        return self.__username

    def _password_for_verification(self) -> str:
        return self.__password

    def __repr__(self) -> str:
        return "<LoginInput redacted>"

    def __reduce__(self):
        raise TypeError("Login input cannot be serialized.")


@dataclass(frozen=True, slots=True)
class LoginAttemptContext:
    """Protection input contains no password; sensitive source/account keys are redacted."""

    username: str = field(repr=False)
    trusted_source_key: str | None = field(default=None, repr=False)


class LoginAttemptDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


class CredentialAttemptOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LoginAttemptProtection(Protocol):
    """Future boundary for rate/resource checks and attempt accounting.

    ``check`` must acquire any bounded verification permit only when returning
    ``ALLOW``. It must account for and release its own resources if it denies or
    raises. For every ``ALLOW``, the orchestrator calls
    ``finish_credential_check`` after verification, including provider failures,
    with ``None`` when no trustworthy credential outcome is available.
    """

    def check(self, attempt: LoginAttemptContext) -> LoginAttemptDecision: ...

    def finish_credential_check(
        self,
        attempt: LoginAttemptContext,
        outcome: CredentialAttemptOutcome | None,
    ) -> None:
        """Record the result and release any concurrency permit acquired by check()."""


class AuthenticationCompletionDecision(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    DENY = "deny"


class AuthenticationCompletionPolicy(Protocol):
    """Trusted server policy; never accept a caller-supplied MFA-complete boolean."""

    def evaluate(
        self, verified: VerifiedCredential
    ) -> AuthenticationCompletionDecision: ...


class LogoutOutcome(StrEnum):
    REVOKED = "revoked"
    ALREADY_REVOKED = "already_revoked"
    SESSION_ABSENT = "session_absent"
    INVALID_TOKEN = "invalid_token"
    REVOCATION_UNCERTAIN = "revocation_uncertain"


@dataclass(frozen=True, slots=True)
class LogoutResult:
    """Cookie-clear instruction is independent from whether server revocation succeeded."""

    outcome: LogoutOutcome
    clear_local_cookie: bool = True


class LoginResult:
    """Minimal successful outcome retaining the existing protected token container."""

    __slots__ = ("user_id", "credential_version", "rehash_recommended", "__session")

    def __init__(
        self,
        verified: VerifiedCredential,
        issued_session: IssuedSession,
    ) -> None:
        object.__setattr__(self, "user_id", verified.user_id)
        object.__setattr__(self, "credential_version", verified.credential_version)
        object.__setattr__(self, "rehash_recommended", verified.rehash_recommended)
        object.__setattr__(self, "_LoginResult__session", issued_session)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Login results are immutable.")

    @property
    def session_id(self) -> UUID:
        return self.__session.session_id

    @property
    def expires_at(self):
        return self.__session.expires_at

    def session_for_cookie_delivery(self) -> IssuedSession:
        """Return the existing protected delivery object without copying the raw token."""

        return self.__session

    def __repr__(self) -> str:
        return (
            f"<LoginResult user_id={self.user_id!r} "
            f"credential_version={self.credential_version!r} "
            f"rehash_recommended={self.rehash_recommended!r}>"
        )

    def __reduce__(self):
        raise TypeError("Login results cannot be serialized.")


class LoginLogoutOrchestrator:
    """Compose offline credential verification, policy gates, and session lifecycle."""

    def __init__(
        self,
        *,
        credentials: CredentialVerificationService,
        sessions: SessionLifecycleService,
        attempt_protection: LoginAttemptProtection,
        completion_policy: AuthenticationCompletionPolicy,
        input_policy: LoginInputPolicy,
    ) -> None:
        self._credentials = credentials
        self._sessions = sessions
        self._attempt_protection = attempt_protection
        self._completion_policy = completion_policy
        self._input_policy = input_policy

    def login(
        self,
        login_input: LoginInput,
        *,
        trusted_source_key: str | None = None,
    ) -> LoginResult:
        if not isinstance(login_input, LoginInput):
            raise LoginRejected(LoginFailureReason.INVALID_INPUT) from None
        username = login_input._username_for_internal_use()
        password = login_input._password_for_verification()
        if (
            not self._input_policy.accepts(username, password)
            or not self._input_policy.accepts_source_key(trusted_source_key)
        ):
            raise LoginRejected(LoginFailureReason.INVALID_INPUT) from None

        attempt = LoginAttemptContext(username, trusted_source_key)
        try:
            decision = self._attempt_protection.check(attempt)
        except Exception:
            raise LoginUnavailable(LoginFailureReason.PROTECTION_UNAVAILABLE) from None
        if decision is LoginAttemptDecision.DENY:
            raise LoginRejected(LoginFailureReason.ATTEMPT_BLOCKED) from None
        if decision is not LoginAttemptDecision.ALLOW:
            raise LoginUnavailable(LoginFailureReason.PROTECTION_UNAVAILABLE) from None

        verified = self._verify_credentials_with_protection(attempt, username, password)

        try:
            completion = self._completion_policy.evaluate(verified)
        except Exception:
            raise LoginUnavailable(LoginFailureReason.COMPLETION_POLICY_UNAVAILABLE) from None
        if completion is AuthenticationCompletionDecision.INCOMPLETE:
            raise LoginRejected(LoginFailureReason.AUTHENTICATION_INCOMPLETE) from None
        if completion is AuthenticationCompletionDecision.DENY:
            raise LoginRejected(LoginFailureReason.AUTHENTICATION_DENIED) from None
        if completion is not AuthenticationCompletionDecision.COMPLETE:
            raise LoginUnavailable(LoginFailureReason.COMPLETION_POLICY_UNAVAILABLE) from None

        try:
            issued = self._sessions.issue(verified)
        except SessionRejected:
            raise LoginRejected(LoginFailureReason.STALE_IDENTITY) from None
        except SessionServiceUnavailable:
            raise LoginUnavailable(LoginFailureReason.SESSION_UNAVAILABLE) from None
        except Exception:
            raise LoginUnavailable(LoginFailureReason.SESSION_UNAVAILABLE) from None

        if not isinstance(issued, IssuedSession):
            raise LoginUnavailable(LoginFailureReason.SESSION_UNAVAILABLE) from None
        return LoginResult(verified, issued)

    def logout(self, raw_token: str) -> LogoutResult:
        """Request only current-token revocation; always let the HTTP layer clear its cookie."""

        try:
            outcome = self._sessions.revoke(raw_token)
        except SessionRejected as error:
            if error.reason is SessionFailureReason.INVALID_TOKEN:
                return LogoutResult(LogoutOutcome.INVALID_TOKEN)
            if error.reason is SessionFailureReason.UNKNOWN_SESSION:
                return LogoutResult(LogoutOutcome.SESSION_ABSENT)
            return LogoutResult(LogoutOutcome.REVOCATION_UNCERTAIN)
        except SessionServiceUnavailable:
            return LogoutResult(LogoutOutcome.REVOCATION_UNCERTAIN)
        except Exception:
            return LogoutResult(LogoutOutcome.REVOCATION_UNCERTAIN)

        if outcome is SessionRevocationResult.REVOKED:
            return LogoutResult(LogoutOutcome.REVOKED)
        if outcome is SessionRevocationResult.ALREADY_REVOKED:
            return LogoutResult(LogoutOutcome.ALREADY_REVOKED)
        if outcome is SessionRevocationResult.NOT_FOUND:
            return LogoutResult(LogoutOutcome.SESSION_ABSENT)
        return LogoutResult(LogoutOutcome.REVOCATION_UNCERTAIN)

    def _verify_credentials_with_protection(
        self,
        attempt: LoginAttemptContext,
        username: str,
        password: str,
    ) -> VerifiedCredential:
        verified: VerifiedCredential | None = None
        outcome: CredentialAttemptOutcome | None = None
        rejection_reason: LoginFailureReason | None = None
        unavailable_reason: LoginFailureReason | None = None
        try:
            candidate = self._credentials.verify(username, password)
        except CredentialRejected:
            outcome = CredentialAttemptOutcome.FAILED
            rejection_reason = LoginFailureReason.CREDENTIALS_REJECTED
        except CredentialVerificationUnavailable:
            unavailable_reason = LoginFailureReason.CREDENTIAL_VERIFICATION_UNAVAILABLE
        except Exception:
            unavailable_reason = LoginFailureReason.CREDENTIAL_VERIFICATION_UNAVAILABLE
        else:
            if (
                isinstance(candidate, VerifiedCredential)
                and isinstance(candidate.user_id, UUID)
                and type(candidate.credential_version) is int
                and candidate.credential_version > 0
                and isinstance(candidate.rehash_recommended, bool)
            ):
                verified = candidate
                outcome = CredentialAttemptOutcome.SUCCEEDED
            else:
                unavailable_reason = LoginFailureReason.CREDENTIAL_VERIFICATION_UNAVAILABLE

        try:
            result = self._attempt_protection.finish_credential_check(attempt, outcome)
        except Exception:
            raise LoginUnavailable(LoginFailureReason.PROTECTION_UNAVAILABLE) from None
        if result is not None:
            raise LoginUnavailable(LoginFailureReason.PROTECTION_UNAVAILABLE) from None
        if rejection_reason is not None:
            raise LoginRejected(rejection_reason) from None
        if unavailable_reason is not None or verified is None:
            raise LoginUnavailable(
                unavailable_reason or LoginFailureReason.CREDENTIAL_VERIFICATION_UNAVAILABLE
            ) from None
        return verified
