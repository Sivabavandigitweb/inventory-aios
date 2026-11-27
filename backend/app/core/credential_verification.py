"""Offline-ready credential verification orchestration with injected repositories.

This service is deliberately not wired to HTTP authentication, persistence, sessions,
authorization, MFA, audit writing, or account provisioning.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import NoReturn, Protocol
from uuid import UUID

from app.core.password_hashing import InvalidStoredPasswordHash, PasswordHashingService


class CredentialFailureReason(StrEnum):
    """Internal failure category; callers must map rejections to one public response."""

    INVALID_INPUT = "invalid_input"
    UNKNOWN_USER = "unknown_user"
    INELIGIBLE_USER = "ineligible_user"
    MISSING_CREDENTIAL = "missing_credential"
    PASSWORD_REJECTED = "password_rejected"
    INCONSISTENT_DATA = "inconsistent_data"
    USER_REPOSITORY_FAILURE = "user_repository_failure"
    CREDENTIAL_REPOSITORY_FAILURE = "credential_repository_failure"
    PASSWORD_PROVIDER_FAILURE = "password_provider_failure"


class CredentialVerificationError(Exception):
    """Safe base error carrying only a non-sensitive internal failure category."""

    public_message = "Credential verification failed."

    def __init__(self, reason: CredentialFailureReason) -> None:
        self.reason = reason
        super().__init__(self.public_message)


class CredentialRejected(CredentialVerificationError):
    """An identity cannot be authenticated; unknown and invalid accounts look alike."""

    public_message = "Credentials are invalid."


class CredentialVerificationUnavailable(CredentialVerificationError):
    """An injected repository or cryptographic provider could not safely complete."""

    public_message = "Credential verification is temporarily unavailable."


@dataclass(frozen=True, slots=True)
class LoginUser:
    """Minimal identity projection needed for local credential verification."""

    user_id: UUID
    username: str = field(repr=False)
    status: str


@dataclass(frozen=True, slots=True)
class PasswordCredentialRecord:
    """Credential projection; the PHC hash is excluded from representations."""

    user_id: UUID
    password_hash: str = field(repr=False)
    credential_version: int


@dataclass(frozen=True, slots=True)
class DummyVerificationCredential:
    """Pre-generated, non-account PHC hash used only for bounded dummy verification."""

    password_hash: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class VerifiedCredential:
    """Minimal successful result; it conveys neither authorization nor a session."""

    user_id: UUID
    credential_version: int
    rehash_recommended: bool


class UsernameCanonicalizer(Protocol):
    """Explicit contract; production normalization rules remain a pending decision."""

    def __call__(self, username: str) -> str: ...


def canonicalize_ascii_username(username: str) -> str:
    """Apply the confirmed lowercase-ASCII login contract without trimming.

    PostgreSQL ``lower(username)`` and this operation agree for ASCII input;
    non-ASCII identifiers are rejected instead of being Unicode-folded.
    """
    if not isinstance(username, str) or not username or not username.isascii():
        raise ValueError("Username must be non-empty ASCII text.")
    if username != username.strip():
        raise ValueError("Username cannot contain surrounding whitespace.")
    return username.lower()


class UserIdentityRepository(Protocol):
    """Return all matches so ambiguous identity resolution can fail closed."""

    def find_by_canonical_username(self, canonical_username: str) -> Sequence[LoginUser]: ...


class PasswordCredentialRepository(Protocol):
    """Retrieve a single local password credential without exposing other user data."""

    def get_for_user(self, user_id: UUID) -> PasswordCredentialRecord | None: ...


class CredentialVerificationService:
    """Verify a local password against injected read-only identity repositories."""

    def __init__(
        self,
        *,
        users: UserIdentityRepository,
        credentials: PasswordCredentialRepository,
        passwords: PasswordHashingService,
        canonicalize_username: UsernameCanonicalizer,
        dummy_credential: DummyVerificationCredential,
    ) -> None:
        if not isinstance(dummy_credential.password_hash, str) or not dummy_credential.password_hash:
            raise ValueError("A configured dummy verification hash is required.")
        self._users = users
        self._credentials = credentials
        self._passwords = passwords
        self._canonicalize_username = canonicalize_username
        self._dummy_credential = dummy_credential

    def verify(self, username: str, password: str) -> VerifiedCredential:
        if not isinstance(username, str) or not username or not isinstance(password, str) or not password:
            self._reject(CredentialFailureReason.INVALID_INPUT, password)

        try:
            canonical_username = self._canonicalize_username(username)
        except Exception:
            self._reject(CredentialFailureReason.INVALID_INPUT, password)
        if not isinstance(canonical_username, str) or not canonical_username:
            self._reject(CredentialFailureReason.INVALID_INPUT, password)

        try:
            matches = self._users.find_by_canonical_username(canonical_username)
        except Exception:
            raise CredentialVerificationUnavailable(
                CredentialFailureReason.USER_REPOSITORY_FAILURE
            ) from None

        if not isinstance(matches, Sequence) or isinstance(matches, (str, bytes)):
            self._unavailable(CredentialFailureReason.INCONSISTENT_DATA, password)
        if len(matches) == 0:
            self._reject(CredentialFailureReason.UNKNOWN_USER, password)
        if len(matches) != 1:
            self._unavailable(CredentialFailureReason.INCONSISTENT_DATA, password)

        user = matches[0]
        if not isinstance(user, LoginUser) or not isinstance(user.user_id, UUID):
            self._unavailable(CredentialFailureReason.INCONSISTENT_DATA, password)
        try:
            stored_canonical_username = self._canonicalize_username(user.username)
        except Exception:
            self._unavailable(CredentialFailureReason.INCONSISTENT_DATA, password)
        if stored_canonical_username != canonical_username:
            self._unavailable(CredentialFailureReason.INCONSISTENT_DATA, password)
        if user.status != "active":
            self._reject(CredentialFailureReason.INELIGIBLE_USER, password)

        try:
            credential = self._credentials.get_for_user(user.user_id)
        except Exception:
            raise CredentialVerificationUnavailable(
                CredentialFailureReason.CREDENTIAL_REPOSITORY_FAILURE
            ) from None

        if credential is None:
            self._reject(CredentialFailureReason.MISSING_CREDENTIAL, password)
        if (
            not isinstance(credential, PasswordCredentialRecord)
            or credential.user_id != user.user_id
            or type(credential.credential_version) is not int
            or credential.credential_version <= 0
            or not isinstance(credential.password_hash, str)
            or not credential.password_hash
        ):
            self._unavailable(CredentialFailureReason.INCONSISTENT_DATA, password)

        try:
            rehash_recommended = self._passwords.needs_rehash(credential.password_hash)
        except InvalidStoredPasswordHash:
            self._unavailable(CredentialFailureReason.INCONSISTENT_DATA, password)
        except Exception:
            raise CredentialVerificationUnavailable(
                CredentialFailureReason.PASSWORD_PROVIDER_FAILURE
            ) from None
        if not isinstance(rehash_recommended, bool):
            self._unavailable(CredentialFailureReason.PASSWORD_PROVIDER_FAILURE, password)

        try:
            password_matches = self._passwords.verify_password(password, credential.password_hash)
        except Exception:
            raise CredentialVerificationUnavailable(
                CredentialFailureReason.PASSWORD_PROVIDER_FAILURE
            ) from None
        if not isinstance(password_matches, bool):
            self._unavailable(CredentialFailureReason.PASSWORD_PROVIDER_FAILURE, password)
        if not password_matches:
            self._reject(
                CredentialFailureReason.PASSWORD_REJECTED, password, perform_dummy=False
            )

        return VerifiedCredential(
            user_id=user.user_id,
            credential_version=credential.credential_version,
            rehash_recommended=rehash_recommended,
        )

    def _reject(
        self,
        reason: CredentialFailureReason,
        password: object,
        *,
        perform_dummy: bool = True,
    ) -> NoReturn:
        if perform_dummy:
            self._dummy_verify(password)
        raise CredentialRejected(reason) from None

    def _unavailable(self, reason: CredentialFailureReason, password: object) -> NoReturn:
        self._dummy_verify(password)
        raise CredentialVerificationUnavailable(reason) from None

    def _dummy_verify(self, password: object) -> None:
        if not isinstance(password, str) or not password:
            return
        try:
            self._passwords.verify_password(password, self._dummy_credential.password_hash)
        except Exception:
            raise CredentialVerificationUnavailable(
                CredentialFailureReason.PASSWORD_PROVIDER_FAILURE
            ) from None
