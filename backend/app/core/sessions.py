"""Provider-independent, offline session lifecycle service.

The service is intentionally not wired to FastAPI, cookies, the production
CredentialVerifier, PostgreSQL, role authorization, MFA, or audit writing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Callable, Protocol
from uuid import UUID, uuid4

from app.core.credential_verification import VerifiedCredential

_SESSION_RANDOM_BYTES = 32
_SESSION_TOKEN_LENGTH = 43
_SESSION_TOKEN_MAX_LENGTH = 64
_TOKEN_COLLISION_RETRIES = 3


class SessionFailureReason(StrEnum):
    INVALID_TOKEN = "invalid_token"
    UNKNOWN_SESSION = "unknown_session"
    REVOKED_SESSION = "revoked_session"
    ABSOLUTE_EXPIRY = "absolute_expiry"
    IDLE_EXPIRY = "idle_expiry"
    INELIGIBLE_ACCOUNT = "ineligible_account"
    CREDENTIAL_MISSING = "credential_missing"
    CREDENTIAL_VERSION_MISMATCH = "credential_version_mismatch"
    STALE_VERIFIED_IDENTITY = "stale_verified_identity"
    INCONSISTENT_DATA = "inconsistent_data"
    REPOSITORY_FAILURE = "repository_failure"
    TOKEN_GENERATION_FAILURE = "token_generation_failure"
    TOKEN_COLLISION = "token_collision"
    CLOCK_FAILURE = "clock_failure"


class SessionRejected(Exception):
    """Generic failure for a token or account state that cannot be accepted."""

    public_message = "Session is invalid or expired."

    def __init__(self, reason: SessionFailureReason) -> None:
        self.reason = reason
        super().__init__(self.public_message)


class SessionServiceUnavailable(Exception):
    """Sanitized failure for token-generation or persistence infrastructure."""

    public_message = "Session service is temporarily unavailable."

    def __init__(self, reason: SessionFailureReason) -> None:
        self.reason = reason
        super().__init__(self.public_message)


class SessionTokenDigestCollision(Exception):
    """Repository signal reserved for a unique token-digest collision."""


class SessionCreationStateChanged(Exception):
    """Atomic repository insert found account state differs from the snapshot."""


class ActivityUpdateResult(StrEnum):
    UPDATED = "updated"
    ALREADY_ADVANCED = "already_advanced"
    SESSION_INVALID = "session_invalid"


class SessionRevocationResult(StrEnum):
    REVOKED = "revoked"
    ALREADY_REVOKED = "already_revoked"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    """Explicit policy values; the ceiling is technical validation, not a default."""

    absolute_lifetime: timedelta
    inactivity_timeout: timedelta
    activity_update_interval: timedelta
    maximum_absolute_lifetime: timedelta

    def __post_init__(self) -> None:
        durations = (
            self.absolute_lifetime,
            self.inactivity_timeout,
            self.activity_update_interval,
            self.maximum_absolute_lifetime,
        )
        if any(not isinstance(value, timedelta) for value in durations):
            raise ValueError("Session policy durations must be timedeltas.")
        if (
            self.absolute_lifetime <= timedelta(0)
            or self.inactivity_timeout <= timedelta(0)
            or self.maximum_absolute_lifetime <= timedelta(0)
            or self.activity_update_interval < timedelta(0)
        ):
            raise ValueError("Session policy durations are invalid.")
        if self.absolute_lifetime > self.maximum_absolute_lifetime:
            raise ValueError("Absolute lifetime exceeds its configured safety ceiling.")
        if self.inactivity_timeout > self.absolute_lifetime:
            raise ValueError("Inactivity timeout cannot exceed absolute lifetime.")
        if self.activity_update_interval >= self.inactivity_timeout:
            raise ValueError("Activity update interval must be shorter than inactivity timeout.")


@dataclass(frozen=True, slots=True)
class CurrentAccountSessionState:
    user_id: UUID
    status: str
    credential_version: int | None


@dataclass(frozen=True, slots=True)
class NewSessionRecord:
    """Persistence input compatible with AuthSession; raw token is never present."""

    session_id: UUID
    user_id: UUID
    token_digest: bytes = field(repr=False)
    credential_version: int
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class StoredSessionRecord:
    """Minimal session row projection; digest is hidden from representations."""

    session_id: UUID
    user_id: UUID
    token_digest: bytes = field(repr=False)
    credential_version: int
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


class SessionRepository(Protocol):
    """Narrow persistence contract; all state-changing DB implementations must be atomic."""

    def create_if_current(self, record: NewSessionRecord) -> None:
        """Insert only if user is active and credential version still matches.

        A future SQL implementation must enforce this in the insert transaction,
        not rely on the preceding account read performed by the service.
        """

    def get_by_token_digest(self, token_digest: bytes) -> StoredSessionRecord | None: ...

    def update_activity_if_current(
        self,
        *,
        session_id: UUID,
        expected_user_id: UUID,
        expected_credential_version: int,
        expected_last_seen_at: datetime,
        checked_at: datetime,
        new_last_seen_at: datetime,
        inactivity_timeout: timedelta,
    ) -> ActivityUpdateResult:
        """Conditionally update without overwriting revocation or newer activity.

        The database operation must also re-check active user status and current
        credential version in the same transaction.
        """

    def revoke_one_if_active(
        self, session_id: UUID, revoked_at: datetime
    ) -> SessionRevocationResult:
        """Set revoked_at only once; report already-revoked rows without replacing it."""

    def revoke_all_for_user(self, user_id: UUID, revoked_at: datetime) -> int:
        """Revoke active rows for exactly one user, preserving existing timestamps."""


class AccountSessionStateRepository(Protocol):
    def get_current_state(self, user_id: UUID) -> CurrentAccountSessionState | None: ...


class IssuedSession:
    """One-time delivery container; representations and generic serialization omit token."""

    __slots__ = ("session_id", "user_id", "expires_at", "__raw_token")

    def __init__(self, session_id: UUID, user_id: UUID, expires_at: datetime, raw_token: str) -> None:
        object.__setattr__(self, "session_id", session_id)
        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "_IssuedSession__raw_token", raw_token)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Issued session results are immutable.")

    def token_for_cookie_delivery(self) -> str:
        """Expose the raw value only at the future secure cookie delivery boundary."""

        return self.__raw_token

    def __repr__(self) -> str:
        return (
            f"<IssuedSession session_id={self.session_id!r} "
            f"user_id={self.user_id!r} expires_at={self.expires_at!r}>"
        )

    def __reduce__(self):
        raise TypeError("Session issuance results cannot be serialized.")


@dataclass(frozen=True, slots=True)
class ValidatedSession:
    session_id: UUID
    user_id: UUID
    credential_version: int


class SessionLifecycleService:
    """Issue, validate, track, and revoke sessions using injected offline ports."""

    def __init__(
        self,
        *,
        sessions: SessionRepository,
        accounts: AccountSessionStateRepository,
        policy: SessionPolicy,
        clock: Callable[[], datetime],
    ) -> None:
        self._sessions = sessions
        self._accounts = accounts
        self._policy = policy
        self._clock = clock

    def issue(self, verified: VerifiedCredential) -> IssuedSession:
        if (
            not isinstance(verified, VerifiedCredential)
            or not isinstance(verified.user_id, UUID)
            or type(verified.credential_version) is not int
            or verified.credential_version <= 0
            or not isinstance(verified.rehash_recommended, bool)
        ):
            raise SessionRejected(SessionFailureReason.STALE_VERIFIED_IDENTITY) from None

        now = self._now()
        current = self._get_account_state(verified.user_id)
        self._check_account_state(current, verified.user_id)
        if current.credential_version != verified.credential_version:
            raise SessionRejected(SessionFailureReason.STALE_VERIFIED_IDENTITY) from None

        try:
            expires_at = now + self._policy.absolute_lifetime
        except OverflowError:
            raise SessionRejected(SessionFailureReason.INCONSISTENT_DATA) from None
        if expires_at <= now:
            raise SessionRejected(SessionFailureReason.INCONSISTENT_DATA) from None

        for attempt in range(_TOKEN_COLLISION_RETRIES):
            raw_token = self._new_token()
            digest = _digest_token(raw_token)
            record = NewSessionRecord(
                session_id=uuid4(),
                user_id=verified.user_id,
                token_digest=digest,
                credential_version=verified.credential_version,
                created_at=now,
                last_seen_at=now,
                expires_at=expires_at,
            )
            try:
                persisted = self._sessions.create_if_current(record)
            except SessionTokenDigestCollision:
                if attempt + 1 == _TOKEN_COLLISION_RETRIES:
                    raise SessionServiceUnavailable(SessionFailureReason.TOKEN_COLLISION) from None
                continue
            except SessionCreationStateChanged:
                raise SessionRejected(SessionFailureReason.STALE_VERIFIED_IDENTITY) from None
            except Exception:
                raise SessionServiceUnavailable(SessionFailureReason.REPOSITORY_FAILURE) from None
            if persisted is not None:
                raise SessionServiceUnavailable(SessionFailureReason.INCONSISTENT_DATA) from None
            return IssuedSession(record.session_id, record.user_id, record.expires_at, raw_token)

        raise SessionServiceUnavailable(SessionFailureReason.TOKEN_COLLISION) from None

    def validate(
        self, raw_token: str, *, update_activity: bool = True
    ) -> ValidatedSession:
        if type(update_activity) is not bool:
            raise SessionRejected(SessionFailureReason.INCONSISTENT_DATA) from None
        digest = _digest_from_input(raw_token)
        now = self._now()
        record = self._get_session(digest)
        account = self._get_account_state(record.user_id)
        self._validate_record(record, digest, account, now)

        if update_activity and self._activity_due(record.last_seen_at, now):
            try:
                outcome = self._sessions.update_activity_if_current(
                    session_id=record.session_id,
                    expected_user_id=record.user_id,
                    expected_credential_version=record.credential_version,
                    expected_last_seen_at=record.last_seen_at,
                    checked_at=now,
                    new_last_seen_at=now,
                    inactivity_timeout=self._policy.inactivity_timeout,
                )
            except Exception:
                raise SessionServiceUnavailable(SessionFailureReason.REPOSITORY_FAILURE) from None
            if outcome is ActivityUpdateResult.SESSION_INVALID:
                raise SessionRejected(SessionFailureReason.INVALID_TOKEN) from None
            if outcome is ActivityUpdateResult.ALREADY_ADVANCED:
                # Re-read both records after a concurrent update; never overwrite newer activity.
                record = self._get_session(digest)
                account = self._get_account_state(record.user_id)
                self._validate_record(record, digest, account, now)
            elif outcome is not ActivityUpdateResult.UPDATED:
                raise SessionServiceUnavailable(SessionFailureReason.INCONSISTENT_DATA) from None

        return ValidatedSession(record.session_id, record.user_id, record.credential_version)

    def revoke(self, raw_token: str) -> SessionRevocationResult:
        digest = _digest_from_input(raw_token)
        record = self._get_session(digest)
        now = self._now()
        self._validate_record_shape(record, digest)
        if record.revoked_at is not None:
            return SessionRevocationResult.ALREADY_REVOKED
        try:
            outcome = self._sessions.revoke_one_if_active(record.session_id, now)
        except Exception:
            raise SessionServiceUnavailable(SessionFailureReason.REPOSITORY_FAILURE) from None
        if not isinstance(outcome, SessionRevocationResult):
            raise SessionServiceUnavailable(SessionFailureReason.INCONSISTENT_DATA) from None
        if outcome is SessionRevocationResult.NOT_FOUND:
            raise SessionRejected(SessionFailureReason.UNKNOWN_SESSION) from None
        return outcome

    def revoke_all_for_user(self, user_id: UUID) -> int:
        """Internal contract for approved reset/deactivation workflows; not an endpoint."""

        if not isinstance(user_id, UUID):
            raise SessionRejected(SessionFailureReason.INCONSISTENT_DATA) from None
        now = self._now()
        try:
            count = self._sessions.revoke_all_for_user(user_id, now)
        except Exception:
            raise SessionServiceUnavailable(SessionFailureReason.REPOSITORY_FAILURE) from None
        if type(count) is not int or count < 0:
            raise SessionServiceUnavailable(SessionFailureReason.INCONSISTENT_DATA) from None
        return count

    def _new_token(self) -> str:
        try:
            token = secrets.token_urlsafe(_SESSION_RANDOM_BYTES)
        except Exception:
            raise SessionServiceUnavailable(SessionFailureReason.TOKEN_GENERATION_FAILURE) from None
        try:
            _decode_token(token)
        except SessionRejected:
            raise SessionServiceUnavailable(SessionFailureReason.TOKEN_GENERATION_FAILURE) from None
        return token

    def _now(self) -> datetime:
        try:
            value = self._clock()
        except Exception:
            raise SessionServiceUnavailable(SessionFailureReason.CLOCK_FAILURE) from None
        normalized = _as_utc(value)
        if normalized is None:
            raise SessionServiceUnavailable(SessionFailureReason.CLOCK_FAILURE) from None
        return normalized

    def _get_session(self, digest: bytes) -> StoredSessionRecord:
        try:
            record = self._sessions.get_by_token_digest(digest)
        except Exception:
            raise SessionServiceUnavailable(SessionFailureReason.REPOSITORY_FAILURE) from None
        if record is None:
            raise SessionRejected(SessionFailureReason.UNKNOWN_SESSION) from None
        self._validate_record_shape(record, digest)
        return record

    def _get_account_state(self, user_id: UUID) -> CurrentAccountSessionState | None:
        try:
            state = self._accounts.get_current_state(user_id)
        except Exception:
            raise SessionServiceUnavailable(SessionFailureReason.REPOSITORY_FAILURE) from None
        if state is not None and (
            not isinstance(state, CurrentAccountSessionState)
            or state.user_id != user_id
            or not isinstance(state.status, str)
            or (state.credential_version is not None and type(state.credential_version) is not int)
        ):
            raise SessionServiceUnavailable(SessionFailureReason.INCONSISTENT_DATA) from None
        return state

    def _check_account_state(
        self, state: CurrentAccountSessionState | None, user_id: UUID
    ) -> None:
        if state is None or state.user_id != user_id:
            raise SessionRejected(SessionFailureReason.CREDENTIAL_MISSING) from None
        if state.status != "active":
            raise SessionRejected(SessionFailureReason.INELIGIBLE_ACCOUNT) from None
        if state.credential_version is None or state.credential_version <= 0:
            raise SessionRejected(SessionFailureReason.CREDENTIAL_MISSING) from None

    def _validate_record_shape(self, record: StoredSessionRecord, digest: bytes) -> None:
        if (
            not isinstance(record, StoredSessionRecord)
            or not isinstance(record.session_id, UUID)
            or not isinstance(record.user_id, UUID)
            or not isinstance(record.token_digest, bytes)
            or len(record.token_digest) != 32
            or not hmac.compare_digest(record.token_digest, digest)
            or type(record.credential_version) is not int
            or record.credential_version <= 0
        ):
            raise SessionServiceUnavailable(SessionFailureReason.INCONSISTENT_DATA) from None

        created = _as_utc(record.created_at)
        last_seen = _as_utc(record.last_seen_at)
        expires = _as_utc(record.expires_at)
        revoked = _as_utc(record.revoked_at) if record.revoked_at is not None else None
        if (
            created is None
            or last_seen is None
            or expires is None
            or (record.revoked_at is not None and revoked is None)
            or last_seen < created
            or expires <= created
            or last_seen >= expires
            or (revoked is not None and revoked < created)
        ):
            raise SessionServiceUnavailable(SessionFailureReason.INCONSISTENT_DATA) from None

    def _validate_record(
        self,
        record: StoredSessionRecord,
        digest: bytes,
        account: CurrentAccountSessionState | None,
        now: datetime,
    ) -> None:
        self._validate_record_shape(record, digest)
        if record.revoked_at is not None:
            raise SessionRejected(SessionFailureReason.REVOKED_SESSION) from None
        created = _as_utc(record.created_at)
        last_seen = _as_utc(record.last_seen_at)
        expires = _as_utc(record.expires_at)
        assert created is not None and last_seen is not None and expires is not None
        if now < created or now < last_seen:
            raise SessionServiceUnavailable(SessionFailureReason.CLOCK_FAILURE) from None
        if now >= expires:
            raise SessionRejected(SessionFailureReason.ABSOLUTE_EXPIRY) from None
        try:
            idle_deadline = last_seen + self._policy.inactivity_timeout
        except OverflowError:
            raise SessionServiceUnavailable(SessionFailureReason.INCONSISTENT_DATA) from None
        if now >= idle_deadline:
            raise SessionRejected(SessionFailureReason.IDLE_EXPIRY) from None
        if account is None or account.credential_version is None:
            raise SessionRejected(SessionFailureReason.CREDENTIAL_MISSING) from None
        if account.status != "active":
            raise SessionRejected(SessionFailureReason.INELIGIBLE_ACCOUNT) from None
        if account.credential_version != record.credential_version:
            raise SessionRejected(SessionFailureReason.CREDENTIAL_VERSION_MISMATCH) from None

    def _activity_due(self, last_seen_at: datetime, now: datetime) -> bool:
        last_seen = _as_utc(last_seen_at)
        assert last_seen is not None
        elapsed = now - last_seen
        return elapsed > timedelta(0) and elapsed >= self._policy.activity_update_interval


def _digest_from_input(raw_token: object) -> bytes:
    try:
        _decode_token(raw_token)
    except SessionRejected:
        raise
    except Exception:
        raise SessionRejected(SessionFailureReason.INVALID_TOKEN) from None
    return hashlib.sha256(raw_token.encode("ascii")).digest()


def _decode_token(token: object) -> bytes:
    if (
        not isinstance(token, str)
        or len(token) > _SESSION_TOKEN_MAX_LENGTH
        or len(token) != _SESSION_TOKEN_LENGTH
        or any(
            character
            not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
            for character in token
        )
    ):
        raise SessionRejected(SessionFailureReason.INVALID_TOKEN) from None
    try:
        decoded = base64.urlsafe_b64decode(token + "=")
    except Exception:
        raise SessionRejected(SessionFailureReason.INVALID_TOKEN) from None
    canonical = base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=")
    if len(decoded) != _SESSION_RANDOM_BYTES or not hmac.compare_digest(canonical, token):
        raise SessionRejected(SessionFailureReason.INVALID_TOKEN) from None
    return decoded


def _digest_token(raw_token: str) -> bytes:
    _decode_token(raw_token)
    return hashlib.sha256(raw_token.encode("ascii")).digest()


def _as_utc(value: object) -> datetime | None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    try:
        if value.utcoffset() is None:
            return None
        return value.astimezone(UTC)
    except (OverflowError, ValueError):
        return None
