from __future__ import annotations

import hashlib
import json
import pickle
import secrets
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.core.credential_verification import VerifiedCredential
from app.core.sessions import (
    ActivityUpdateResult,
    CurrentAccountSessionState,
    NewSessionRecord,
    SessionCreationStateChanged,
    SessionFailureReason,
    SessionLifecycleService,
    SessionPolicy,
    SessionRejected,
    SessionRevocationResult,
    SessionServiceUnavailable,
    SessionTokenDigestCollision,
    StoredSessionRecord,
    ValidatedSession,
    _digest_token,
)

USER_ID = UUID("10000000-0000-4000-8000-000000000001")
OTHER_USER_ID = UUID("20000000-0000-4000-8000-000000000002")
SESSION_ID = UUID("30000000-0000-4000-8000-000000000003")
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
_DEFAULT_ACCOUNT_STATE = object()


class FakeClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class FakeAccountRepository:
    def __init__(
        self,
        state: CurrentAccountSessionState | None | object = _DEFAULT_ACCOUNT_STATE,
        *,
        user_id: UUID = USER_ID,
    ) -> None:
        if state is _DEFAULT_ACCOUNT_STATE:
            self.states = {user_id: CurrentAccountSessionState(user_id, "active", 3)}
        elif state is None:
            self.states = {}
        else:
            self.states = {user_id: state}
        self.failure: Exception | None = None
        self.lookups: list[UUID] = []

    def get_current_state(self, user_id: UUID) -> CurrentAccountSessionState | None:
        self.lookups.append(user_id)
        if self.failure is not None:
            raise self.failure
        return self.states.get(user_id)


class FakeSessionRepository:
    def __init__(self, accounts: FakeAccountRepository | None = None) -> None:
        self.accounts = accounts
        self.records_by_digest: dict[bytes, StoredSessionRecord] = {}
        self.records_by_id: dict[UUID, bytes] = {}
        self.created: list[NewSessionRecord] = []
        self.updated: list[tuple[UUID, datetime]] = []
        self.revoked: list[tuple[UUID, datetime]] = []
        self.revoked_users: list[tuple[UUID, datetime]] = []
        self.failure_on: str | None = None
        self.collision_digests: set[bytes] = set()
        self.create_state_changed = False
        self.activity_outcome: ActivityUpdateResult | None = None
        self.concurrent_activity_at: datetime | None = None

    def create_if_current(self, record: NewSessionRecord) -> None:
        if self.failure_on == "create":
            raise RuntimeError("session insert detail and token")
        if self.create_state_changed:
            raise SessionCreationStateChanged
        if record.token_digest in self.collision_digests or record.token_digest in self.records_by_digest:
            raise SessionTokenDigestCollision
        self.created.append(record)
        stored = StoredSessionRecord(
            session_id=record.session_id,
            user_id=record.user_id,
            token_digest=record.token_digest,
            credential_version=record.credential_version,
            created_at=record.created_at,
            last_seen_at=record.last_seen_at,
            expires_at=record.expires_at,
            revoked_at=None,
        )
        self.records_by_digest[record.token_digest] = stored
        self.records_by_id[record.session_id] = record.token_digest

    def get_by_token_digest(self, token_digest: bytes) -> StoredSessionRecord | None:
        if self.failure_on == "lookup":
            raise RuntimeError("database locator and digest")
        return self.records_by_digest.get(token_digest)

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
        if self.failure_on == "activity":
            raise RuntimeError("activity update SQL")
        digest = self.records_by_id[session_id]
        current = self.records_by_digest[digest]
        if self.activity_outcome is not None:
            outcome = self.activity_outcome
            self.activity_outcome = None
            if outcome is ActivityUpdateResult.ALREADY_ADVANCED:
                self.records_by_digest[digest] = replace(
                    current, last_seen_at=self.concurrent_activity_at or new_last_seen_at
                )
            return outcome
        if (
            current.revoked_at is not None
            or current.user_id != expected_user_id
            or current.credential_version != expected_credential_version
            or current.expires_at <= checked_at
            or current.last_seen_at + inactivity_timeout <= checked_at
        ):
            return ActivityUpdateResult.SESSION_INVALID
        if current.last_seen_at != expected_last_seen_at:
            return ActivityUpdateResult.ALREADY_ADVANCED
        if new_last_seen_at < current.last_seen_at:
            return ActivityUpdateResult.SESSION_INVALID
        self.updated.append((session_id, new_last_seen_at))
        self.records_by_digest[digest] = replace(current, last_seen_at=new_last_seen_at)
        return ActivityUpdateResult.UPDATED

    def revoke_one_if_active(
        self, session_id: UUID, revoked_at: datetime
    ) -> SessionRevocationResult:
        if self.failure_on == "revoke":
            raise RuntimeError("revoke database error")
        digest = self.records_by_id.get(session_id)
        if digest is None:
            return SessionRevocationResult.NOT_FOUND
        current = self.records_by_digest[digest]
        if current.revoked_at is not None:
            return SessionRevocationResult.ALREADY_REVOKED
        self.revoked.append((session_id, revoked_at))
        self.records_by_digest[digest] = replace(current, revoked_at=revoked_at)
        return SessionRevocationResult.REVOKED

    def revoke_all_for_user(self, user_id: UUID, revoked_at: datetime) -> int:
        if self.failure_on == "revoke_all":
            raise RuntimeError("revoke all database error")
        self.revoked_users.append((user_id, revoked_at))
        count = 0
        for digest, current in list(self.records_by_digest.items()):
            if current.user_id == user_id and current.revoked_at is None:
                self.records_by_digest[digest] = replace(current, revoked_at=revoked_at)
                count += 1
        return count


def make_policy(
    *,
    absolute: timedelta = timedelta(hours=8),
    idle: timedelta = timedelta(minutes=30),
    activity_interval: timedelta = timedelta(minutes=5),
    maximum: timedelta = timedelta(days=1),
) -> SessionPolicy:
    return SessionPolicy(absolute, idle, activity_interval, maximum)


def make_service(
    *,
    clock: FakeClock | None = None,
    accounts: FakeAccountRepository | None = None,
    sessions: FakeSessionRepository | None = None,
    policy: SessionPolicy | None = None,
) -> tuple[SessionLifecycleService, FakeSessionRepository, FakeAccountRepository, FakeClock]:
    active_clock = clock or FakeClock()
    account_repo = accounts or FakeAccountRepository()
    session_repo = sessions or FakeSessionRepository(account_repo)
    if session_repo.accounts is None:
        session_repo.accounts = account_repo
    return (
        SessionLifecycleService(
            sessions=session_repo,
            accounts=account_repo,
            policy=policy or make_policy(),
            clock=active_clock,
        ),
        session_repo,
        account_repo,
        active_clock,
    )


def stored_record(
    token: str,
    *,
    session_id: UUID = SESSION_ID,
    user_id: UUID = USER_ID,
    credential_version: int = 3,
    created_at: datetime = NOW,
    last_seen_at: datetime = NOW,
    expires_at: datetime = NOW + timedelta(hours=8),
    revoked_at: datetime | None = None,
) -> StoredSessionRecord:
    return StoredSessionRecord(
        session_id=session_id,
        user_id=user_id,
        token_digest=_digest_token(token),
        credential_version=credential_version,
        created_at=created_at,
        last_seen_at=last_seen_at,
        expires_at=expires_at,
        revoked_at=revoked_at,
    )


def register_record(repository: FakeSessionRepository, record: StoredSessionRecord) -> None:
    repository.records_by_digest[record.token_digest] = record
    repository.records_by_id[record.session_id] = record.token_digest


def test_policy_requires_explicit_valid_durations() -> None:
    with pytest.raises(ValueError):
        SessionPolicy(timedelta(0), timedelta(minutes=1), timedelta(0), timedelta(days=1))
    with pytest.raises(ValueError):
        SessionPolicy(timedelta(hours=1), timedelta(hours=2), timedelta(0), timedelta(days=1))
    with pytest.raises(ValueError):
        SessionPolicy(timedelta(hours=2), timedelta(minutes=1), timedelta(minutes=1), timedelta(hours=1))
    with pytest.raises(ValueError):
        SessionPolicy(timedelta(hours=1), timedelta(minutes=5), timedelta(minutes=5), timedelta(days=1))


def test_issue_generates_canonical_secure_token_and_persists_only_sha256_digest() -> None:
    service, repository, _, _ = make_service()

    issued = service.issue(VerifiedCredential(USER_ID, 3, False))
    raw_token = issued.token_for_cookie_delivery()
    decoded = __import__("base64").urlsafe_b64decode(raw_token + "=")

    assert len(decoded) == 32
    assert len(raw_token) == 43
    assert all(char.isalnum() or char in "-_" for char in raw_token)
    assert len(repository.created) == 1
    record = repository.created[0]
    assert record.token_digest == hashlib.sha256(raw_token.encode("ascii")).digest()
    assert len(record.token_digest) == 32
    assert not hasattr(record, "raw_token")
    assert raw_token not in repr(record)
    assert raw_token not in repr(issued)
    assert "token" not in repr(issued).lower()
    with pytest.raises(TypeError):
        json.dumps(issued)
    with pytest.raises(TypeError):
        pickle.dumps(issued)


def test_issued_session_is_immutable_and_token_has_dedicated_delivery_accessor() -> None:
    service, _, _, _ = make_service()
    issued = service.issue(VerifiedCredential(USER_ID, 3, False))
    with pytest.raises(AttributeError):
        issued.user_id = OTHER_USER_ID
    assert isinstance(issued.token_for_cookie_delivery(), str)


def test_repeated_issue_calls_return_independent_tokens_and_sessions() -> None:
    service, repository, _, _ = make_service()
    first = service.issue(VerifiedCredential(USER_ID, 3, False))
    second = service.issue(VerifiedCredential(USER_ID, 3, False))

    assert first.token_for_cookie_delivery() != second.token_for_cookie_delivery()
    assert len(repository.created) == 2
    assert repository.created[0].user_id == repository.created[1].user_id == USER_ID
    assert repository.created[0].session_id != repository.created[1].session_id


def test_issue_rejects_inactive_missing_and_stale_account_state() -> None:
    for state, reason in (
        (CurrentAccountSessionState(USER_ID, "inactive", 3), SessionFailureReason.INELIGIBLE_ACCOUNT),
        (None, SessionFailureReason.CREDENTIAL_MISSING),
        (CurrentAccountSessionState(USER_ID, "active", None), SessionFailureReason.CREDENTIAL_MISSING),
        (CurrentAccountSessionState(USER_ID, "active", 2), SessionFailureReason.STALE_VERIFIED_IDENTITY),
    ):
        account_repo = FakeAccountRepository(state)
        service, repository, _, _ = make_service(accounts=account_repo)
        with pytest.raises(SessionRejected) as error:
            service.issue(VerifiedCredential(USER_ID, 3, False))
        assert error.value.reason is reason
        assert not repository.created


@pytest.mark.parametrize(
    "identity",
    [
        object(),
        VerifiedCredential(USER_ID, 0, False),
        VerifiedCredential(USER_ID, True, False),
        VerifiedCredential(USER_ID, 3, 1),  # type: ignore[arg-type]
    ],
)
def test_issue_rejects_invalid_verified_identity_contract(identity: object) -> None:
    service, repository, accounts, _ = make_service()
    with pytest.raises(SessionRejected):
        service.issue(identity)  # type: ignore[arg-type]
    assert accounts.lookups == []
    assert not repository.created


def test_issue_does_not_return_raw_token_if_persistence_outcome_is_uncertain() -> None:
    _, repository, _, _ = make_service()
    repository.failure_on = "create"
    service, _, _, _ = make_service(sessions=repository)

    with pytest.raises(SessionServiceUnavailable) as error:
        service.issue(VerifiedCredential(USER_ID, 3, False))

    assert error.value.reason is SessionFailureReason.REPOSITORY_FAILURE
    assert error.value.__cause__ is None


def test_issue_retries_only_recognized_digest_collision(monkeypatch: pytest.MonkeyPatch) -> None:
    tokens = [secrets.token_urlsafe(32), secrets.token_urlsafe(32)]
    expected_token = tokens[1]
    service, repository, _, _ = make_service()
    repository.collision_digests.add(_digest_token(tokens[0]))
    monkeypatch.setattr("app.core.sessions.secrets.token_urlsafe", lambda _: tokens.pop(0))

    issued = service.issue(VerifiedCredential(USER_ID, 3, False))

    assert issued.token_for_cookie_delivery() == expected_token
    assert len(repository.created) == 1


def test_issue_stops_after_bounded_collisions(monkeypatch: pytest.MonkeyPatch) -> None:
    token = secrets.token_urlsafe(32)
    service, repository, _, _ = make_service()
    repository.collision_digests.add(_digest_token(token))
    monkeypatch.setattr("app.core.sessions.secrets.token_urlsafe", lambda _: token)

    with pytest.raises(SessionServiceUnavailable) as error:
        service.issue(VerifiedCredential(USER_ID, 3, False))

    assert error.value.reason is SessionFailureReason.TOKEN_COLLISION
    assert len(repository.created) == 0


def test_token_generation_failure_returns_no_issuance_result(monkeypatch: pytest.MonkeyPatch) -> None:
    service, repository, _, _ = make_service()

    def fail_generation(_: int) -> str:
        raise RuntimeError("random source detail")

    monkeypatch.setattr("app.core.sessions.secrets.token_urlsafe", fail_generation)
    with pytest.raises(SessionServiceUnavailable) as error:
        service.issue(VerifiedCredential(USER_ID, 3, False))

    assert error.value.reason is SessionFailureReason.TOKEN_GENERATION_FAILURE
    assert error.value.__cause__ is None
    assert repository.created == []


def test_malformed_noncanonical_token_is_rejected_without_repository_lookup() -> None:
    service, repository, _, _ = make_service()

    with pytest.raises(SessionRejected) as error:
        service.validate("A" * 42 + "B")

    assert error.value.reason is SessionFailureReason.INVALID_TOKEN
    assert repository.records_by_digest == {}


def test_atomic_issue_state_change_returns_no_token() -> None:
    service, repository, _, _ = make_service()
    repository.create_state_changed = True

    with pytest.raises(SessionRejected) as error:
        service.issue(VerifiedCredential(USER_ID, 3, False))

    assert error.value.reason is SessionFailureReason.STALE_VERIFIED_IDENTITY
    assert repository.created == []


def test_validate_returns_minimal_identity_and_updates_activity_after_threshold() -> None:
    service, repository, _, clock = make_service()
    issued = service.issue(VerifiedCredential(USER_ID, 3, False))
    token = issued.token_for_cookie_delivery()
    clock.value = NOW + timedelta(minutes=5)

    validated = service.validate(token)

    assert validated == ValidatedSession(repository.created[0].session_id, USER_ID, 3)
    assert repository.updated == [(validated.session_id, clock.value)]
    stored = repository.records_by_digest[hashlib.sha256(token.encode("ascii")).digest()]
    assert stored.last_seen_at == clock.value
    assert stored.expires_at == NOW + timedelta(hours=8)
    assert not hasattr(validated, "token_digest")
    assert not hasattr(validated, "roles")
    assert not hasattr(validated, "permissions")
    assert token not in repr(validated)


def test_read_only_session_check_does_not_extend_idle_timeout() -> None:
    service, repository, _, clock = make_service()
    issued = service.issue(VerifiedCredential(USER_ID, 3, False))
    token = issued.token_for_cookie_delivery()
    stored_digest = hashlib.sha256(token.encode("ascii")).digest()

    clock.value = NOW + timedelta(minutes=5)
    service.validate(token, update_activity=False)
    assert repository.updated == []
    assert repository.records_by_digest[stored_digest].last_seen_at == NOW

    clock.value = NOW + timedelta(minutes=30)
    with pytest.raises(SessionRejected) as error:
        service.validate(token, update_activity=False)

    assert error.value.reason is SessionFailureReason.IDLE_EXPIRY
    assert repository.updated == []


@pytest.mark.parametrize(
    ("token", "reason"),
    [
        ("bad", SessionFailureReason.INVALID_TOKEN),
        ("x" * 1000, SessionFailureReason.INVALID_TOKEN),
        ("A" * 43, SessionFailureReason.UNKNOWN_SESSION),
    ],
)
def test_invalid_or_unknown_tokens_are_rejected_before_activity_update(token: str, reason) -> None:
    service, repository, _, _ = make_service()
    with pytest.raises(SessionRejected) as error:
        service.validate(token)
    assert error.value.reason is reason
    assert repository.updated == []


def test_validate_rejects_revoked_session_without_activity_update() -> None:
    token = secrets.token_urlsafe(32)
    _, repository, _, _ = make_service()
    register_record(
        repository,
        stored_record(
            token,
            created_at=NOW - timedelta(minutes=10),
            last_seen_at=NOW - timedelta(minutes=10),
            revoked_at=NOW - timedelta(minutes=1),
        ),
    )
    service, _, _, _ = make_service(sessions=repository)

    with pytest.raises(SessionRejected) as error:
        service.validate(token)

    assert error.value.reason is SessionFailureReason.REVOKED_SESSION
    assert repository.updated == []


@pytest.mark.parametrize(
    ("expires_at", "last_seen_at", "now", "reason"),
    [
            (
                NOW,
                NOW - timedelta(minutes=1),
                NOW,
                SessionFailureReason.ABSOLUTE_EXPIRY,
            ),
        (
            NOW + timedelta(hours=1),
                NOW - timedelta(minutes=30),
            NOW,
            SessionFailureReason.IDLE_EXPIRY,
        ),
    ],
)
def test_exact_expiration_boundaries_reject(
    expires_at: datetime,
    last_seen_at: datetime,
    now: datetime,
    reason: SessionFailureReason,
) -> None:
    token = secrets.token_urlsafe(32)
    _, repository, _, _ = make_service()
    register_record(
        repository,
        stored_record(
            token,
            created_at=last_seen_at,
            expires_at=expires_at,
            last_seen_at=last_seen_at,
        ),
    )
    service, _, _, _ = make_service(sessions=repository, clock=FakeClock(now))

    with pytest.raises(SessionRejected) as error:
        service.validate(token)

    assert error.value.reason is reason
    assert repository.updated == []


def test_session_valid_one_microsecond_before_expiry_boundary() -> None:
    token = secrets.token_urlsafe(32)
    now = NOW + timedelta(minutes=29, seconds=59, microseconds=999999)
    _, repository, accounts, _ = make_service()
    register_record(repository, stored_record(token))
    service, _, _, _ = make_service(sessions=repository, accounts=accounts, clock=FakeClock(now))

    assert service.validate(token).user_id == USER_ID


@pytest.mark.parametrize(
    ("account_state", "record_version", "reason"),
    [
        (None, 3, SessionFailureReason.CREDENTIAL_MISSING),
        (CurrentAccountSessionState(USER_ID, "inactive", 3), 3, SessionFailureReason.INELIGIBLE_ACCOUNT),
        (CurrentAccountSessionState(USER_ID, "active", None), 3, SessionFailureReason.CREDENTIAL_MISSING),
        (CurrentAccountSessionState(USER_ID, "active", 4), 3, SessionFailureReason.CREDENTIAL_VERSION_MISMATCH),
    ],
)
def test_validate_rejects_missing_inactive_or_changed_credentials(
    account_state: CurrentAccountSessionState | None,
    record_version: int,
    reason: SessionFailureReason,
) -> None:
    token = secrets.token_urlsafe(32)
    _, repository, _, _ = make_service()
    register_record(repository, stored_record(token, credential_version=record_version))
    accounts = FakeAccountRepository(account_state)
    service, _, _, _ = make_service(sessions=repository, accounts=accounts)

    with pytest.raises(SessionRejected) as error:
        service.validate(token)

    assert error.value.reason is reason
    assert repository.updated == []


def test_validation_rejects_session_digest_and_timestamp_inconsistency() -> None:
    token = secrets.token_urlsafe(32)
    _, repository, _, _ = make_service()
    bad = replace(stored_record(token), token_digest=b"x" * 32)
    repository.records_by_digest[_digest_token(token)] = bad
    service, _, _, _ = make_service(sessions=repository)

    with pytest.raises(SessionServiceUnavailable) as error:
        service.validate(token)

    assert error.value.reason is SessionFailureReason.INCONSISTENT_DATA


def test_session_repository_lookup_failure_is_sanitized() -> None:
    token = secrets.token_urlsafe(32)
    _, repository, _, _ = make_service()
    repository.failure_on = "lookup"
    service, _, _, _ = make_service(sessions=repository)

    with pytest.raises(SessionServiceUnavailable) as error:
        service.validate(token)

    assert error.value.reason is SessionFailureReason.REPOSITORY_FAILURE
    assert "database locator" not in str(error.value)
    assert error.value.__cause__ is None


def test_clock_anomaly_fails_closed_and_does_not_update_activity() -> None:
    token = secrets.token_urlsafe(32)
    _, repository, _, _ = make_service()
    register_record(repository, stored_record(token))
    service, _, _, _ = make_service(
        sessions=repository, clock=FakeClock(NOW - timedelta(seconds=1))
    )

    with pytest.raises(SessionServiceUnavailable) as error:
        service.validate(token)

    assert error.value.reason is SessionFailureReason.CLOCK_FAILURE
    assert repository.updated == []


def test_activity_update_failure_is_sanitized_and_session_is_not_returned() -> None:
    token = secrets.token_urlsafe(32)
    _, repository, _, _ = make_service()
    register_record(repository, stored_record(token))
    repository.failure_on = "activity"
    service, _, _, _ = make_service(
        sessions=repository, clock=FakeClock(NOW + timedelta(minutes=5))
    )

    with pytest.raises(SessionServiceUnavailable) as error:
        service.validate(token)

    assert error.value.reason is SessionFailureReason.REPOSITORY_FAILURE
    assert "SQL" not in str(error.value)
    assert error.value.__cause__ is None


def test_stale_activity_update_reloads_and_never_moves_timestamp_backwards() -> None:
    token = secrets.token_urlsafe(32)
    _, repository, _, _ = make_service()
    register_record(repository, stored_record(token))
    now = NOW + timedelta(minutes=5)
    repository.activity_outcome = ActivityUpdateResult.ALREADY_ADVANCED
    repository.concurrent_activity_at = now
    service, _, _, _ = make_service(sessions=repository, clock=FakeClock(now))

    assert service.validate(token).user_id == USER_ID
    stored = repository.records_by_digest[_digest_token(token)]
    assert stored.last_seen_at == now
    assert repository.updated == []


def test_concurrent_revocation_wins_over_activity_update() -> None:
    token = secrets.token_urlsafe(32)
    _, repository, _, _ = make_service()
    register_record(repository, stored_record(token))
    repository.activity_outcome = ActivityUpdateResult.SESSION_INVALID
    service, _, _, _ = make_service(
        sessions=repository, clock=FakeClock(NOW + timedelta(minutes=5))
    )

    with pytest.raises(SessionRejected):
        service.validate(token)


def test_individual_revocation_is_idempotent_and_independent() -> None:
    _, repository, _, _ = make_service()
    service, _, _, _ = make_service(sessions=repository)
    first = service.issue(VerifiedCredential(USER_ID, 3, False))
    second = service.issue(VerifiedCredential(USER_ID, 3, False))
    first_token = first.token_for_cookie_delivery()
    second_token = second.token_for_cookie_delivery()

    assert service.revoke(first_token) is SessionRevocationResult.REVOKED
    first_revocation = repository.records_by_digest[_digest_token(first_token)].revoked_at
    assert service.revoke(first_token) is SessionRevocationResult.ALREADY_REVOKED
    assert repository.records_by_digest[_digest_token(first_token)].revoked_at == first_revocation
    assert service.validate(second_token).user_id == USER_ID
    with pytest.raises(SessionRejected):
        service.validate(first_token)


def test_revoke_repository_failure_is_sanitized() -> None:
    _, repository, _, _ = make_service()
    service, _, _, _ = make_service(sessions=repository)
    issued = service.issue(VerifiedCredential(USER_ID, 3, False))
    repository.failure_on = "revoke"

    with pytest.raises(SessionServiceUnavailable) as error:
        service.revoke(issued.token_for_cookie_delivery())

    assert error.value.reason is SessionFailureReason.REPOSITORY_FAILURE
    assert error.value.__cause__ is None


def test_user_wide_revocation_revokes_only_active_sessions_for_target_user() -> None:
    _, repository, _, _ = make_service()
    service, _, _, _ = make_service(sessions=repository)
    first = service.issue(VerifiedCredential(USER_ID, 3, False))
    second = service.issue(VerifiedCredential(USER_ID, 3, False))
    other_account = FakeAccountRepository(
        CurrentAccountSessionState(OTHER_USER_ID, "active", 9),
        user_id=OTHER_USER_ID,
    )
    other_repo = FakeSessionRepository(other_account)
    other_service, _, _, _ = make_service(sessions=other_repo, accounts=other_account)
    other = other_service.issue(VerifiedCredential(OTHER_USER_ID, 9, False))

    assert service.revoke_all_for_user(USER_ID) == 2
    assert service.revoke_all_for_user(USER_ID) == 0
    assert repository.records_by_digest[_digest_token(first.token_for_cookie_delivery())].revoked_at is not None
    assert repository.records_by_digest[_digest_token(second.token_for_cookie_delivery())].revoked_at is not None
    assert other_service.validate(other.token_for_cookie_delivery()).user_id == OTHER_USER_ID


def test_session_record_representation_never_contains_raw_token_or_digest() -> None:
    token = secrets.token_urlsafe(32)
    record = NewSessionRecord(
        session_id=SESSION_ID,
        user_id=USER_ID,
        token_digest=_digest_token(token),
        credential_version=3,
        created_at=NOW,
        last_seen_at=NOW,
        expires_at=NOW + timedelta(hours=8),
    )

    assert token not in repr(record)
    assert record.token_digest.hex() not in repr(record)
    assert not hasattr(record, "raw_token")
    assert len(record.token_digest) == 32


def test_account_repository_failure_is_sanitized() -> None:
    accounts = FakeAccountRepository()
    accounts.failure = RuntimeError("user status and credential version secret")
    service, repository, _, _ = make_service(accounts=accounts)

    with pytest.raises(SessionServiceUnavailable) as error:
        service.issue(VerifiedCredential(USER_ID, 3, False))

    assert error.value.reason is SessionFailureReason.REPOSITORY_FAILURE
    assert "credential version secret" not in str(error.value)
    assert error.value.__cause__ is None


def test_utc_offset_clock_is_normalized_to_utc() -> None:
    offset_time = NOW.astimezone(timezone(timedelta(hours=5, minutes=30)))
    service, repository, _, _ = make_service(clock=FakeClock(offset_time))
    issued = service.issue(VerifiedCredential(USER_ID, 3, False))

    assert repository.created[0].created_at.tzinfo is UTC
    assert issued.expires_at == NOW + timedelta(hours=8)
