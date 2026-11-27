from __future__ import annotations

import json
import secrets
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.core.argon2_passwords import (
    Argon2CostParameters,
    Argon2idPasswordBackend,
    Argon2VerificationLimits,
)
from app.core.credential_verification import (
    CredentialFailureReason,
    CredentialRejected,
    CredentialVerificationService,
    CredentialVerificationUnavailable,
    DummyVerificationCredential,
    LoginUser,
    PasswordCredentialRecord,
    VerifiedCredential,
)
from app.core.login_orchestration import (
    AuthenticationCompletionDecision,
    CredentialAttemptOutcome,
    LoginAttemptContext,
    LoginAttemptDecision,
    LoginFailureReason,
    LoginInput,
    LoginInputPolicy,
    LoginLogoutOrchestrator,
    LoginRejected,
    LoginResult,
    LoginUnavailable,
    LogoutOutcome,
)
from app.core.password_hashing import PasswordHashingService
from app.core.sessions import (
    ActivityUpdateResult,
    CurrentAccountSessionState,
    NewSessionRecord,
    SessionLifecycleService,
    SessionPolicy,
    SessionRejected,
    SessionRevocationResult,
    StoredSessionRecord,
    _digest_token,
)

USER_ID = UUID("10000000-0000-4000-8000-000000000001")
OTHER_USER_ID = UUID("20000000-0000-4000-8000-000000000002")
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)
PASSWORD = "Fictional login test password"


class FakeClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeAccounts:
    def __init__(self) -> None:
        self.states = {USER_ID: CurrentAccountSessionState(USER_ID, "active", 4)}
        self.failure: Exception | None = None

    def get_current_state(self, user_id: UUID):
        if self.failure:
            raise self.failure
        return self.states.get(user_id)


class FakeSessionStore:
    def __init__(self, accounts: FakeAccounts) -> None:
        self.accounts = accounts
        self.by_digest: dict[bytes, StoredSessionRecord] = {}
        self.by_id: dict[UUID, bytes] = {}
        self.created: list[NewSessionRecord] = []
        self.activity_updates: list[tuple[UUID, datetime]] = []
        self.revocations: list[tuple[UUID, datetime]] = []
        self.failure_on: str | None = None
        self.uncertain_create = False
        self.uncertain_revoke = False

    def create_if_current(self, record: NewSessionRecord) -> None:
        if self.failure_on == "create":
            raise RuntimeError("database commit detail")
        current = self.accounts.states.get(record.user_id)
        if (
            current is None
            or current.status != "active"
            or current.credential_version != record.credential_version
        ):
            from app.core.sessions import SessionCreationStateChanged

            raise SessionCreationStateChanged
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
        self.created.append(record)
        self.by_digest[record.token_digest] = stored
        self.by_id[record.session_id] = record.token_digest
        if self.uncertain_create:
            raise RuntimeError("connection lost after commit")

    def get_by_token_digest(self, token_digest: bytes):
        if self.failure_on == "lookup":
            raise RuntimeError("session lookup detail")
        return self.by_digest.get(token_digest)

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
            raise RuntimeError("activity update detail")
        digest = self.by_id[session_id]
        current = self.by_digest[digest]
        account = self.accounts.states.get(current.user_id)
        if (
            current.revoked_at is not None
            or current.expires_at <= checked_at
            or current.last_seen_at + inactivity_timeout <= checked_at
            or current.user_id != expected_user_id
            or current.credential_version != expected_credential_version
            or account is None
            or account.status != "active"
            or account.credential_version != expected_credential_version
        ):
            return ActivityUpdateResult.SESSION_INVALID
        if current.last_seen_at != expected_last_seen_at:
            return ActivityUpdateResult.ALREADY_ADVANCED
        self.activity_updates.append((session_id, new_last_seen_at))
        self.by_digest[digest] = replace(current, last_seen_at=new_last_seen_at)
        return ActivityUpdateResult.UPDATED

    def revoke_one_if_active(self, session_id: UUID, revoked_at: datetime):
        if self.failure_on == "revoke":
            raise RuntimeError("logout persistence error")
        digest = self.by_id.get(session_id)
        if digest is None:
            return SessionRevocationResult.NOT_FOUND
        current = self.by_digest[digest]
        if current.revoked_at is not None:
            return SessionRevocationResult.ALREADY_REVOKED
        self.by_digest[digest] = replace(current, revoked_at=revoked_at)
        self.revocations.append((session_id, revoked_at))
        if self.uncertain_revoke:
            raise RuntimeError("connection lost after revocation commit")
        return SessionRevocationResult.REVOKED

    def revoke_all_for_user(self, user_id: UUID, revoked_at: datetime) -> int:
        count = 0
        for digest, current in list(self.by_digest.items()):
            if current.user_id == user_id and current.revoked_at is None:
                self.by_digest[digest] = replace(current, revoked_at=revoked_at)
                count += 1
        return count


class FakeCredentials:
    def __init__(self, result: object = VerifiedCredential(USER_ID, 4, False)) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def verify(self, username: str, password: str):
        self.calls.append((username, password))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeAttemptProtection:
    def __init__(self) -> None:
        self.decision = LoginAttemptDecision.ALLOW
        self.check_error: Exception | None = None
        self.finish_error: Exception | None = None
        self.checked: list[LoginAttemptContext] = []
        self.outcomes: list[tuple[LoginAttemptContext, CredentialAttemptOutcome]] = []

    def check(self, attempt: LoginAttemptContext):
        self.checked.append(attempt)
        if self.check_error:
            raise self.check_error
        return self.decision

    def finish_credential_check(
        self, attempt: LoginAttemptContext, outcome: CredentialAttemptOutcome | None
    ) -> None:
        if self.finish_error:
            raise self.finish_error
        self.outcomes.append((attempt, outcome))


class FakeCompletionPolicy:
    def __init__(self) -> None:
        self.decision = AuthenticationCompletionDecision.COMPLETE
        self.failure: Exception | None = None
        self.identities: list[VerifiedCredential] = []

    def evaluate(self, verified: VerifiedCredential):
        self.identities.append(verified)
        if self.failure:
            raise self.failure
        return self.decision


def make_test_session_policy() -> SessionPolicy:
    return SessionPolicy(
        absolute_lifetime=timedelta(hours=8),
        inactivity_timeout=timedelta(minutes=30),
        activity_update_interval=timedelta(minutes=5),
        maximum_absolute_lifetime=timedelta(days=1),
    )


def make_session_service(
    *,
    clock: FakeClock | None = None,
    accounts: FakeAccounts | None = None,
    store: FakeSessionStore | None = None,
) -> tuple[SessionLifecycleService, FakeSessionStore, FakeAccounts, FakeClock]:
    active_clock = clock or FakeClock()
    account_repo = accounts or FakeAccounts()
    session_repo = store or FakeSessionStore(account_repo)
    return (
        SessionLifecycleService(
            sessions=session_repo,
            accounts=account_repo,
            policy=make_test_session_policy(),
            clock=active_clock,
        ),
        session_repo,
        account_repo,
        active_clock,
    )


def make_orchestrator(
    *,
    credentials: FakeCredentials | None = None,
    sessions: SessionLifecycleService | None = None,
    attempt_protection: FakeAttemptProtection | None = None,
    completion: FakeCompletionPolicy | None = None,
) -> tuple[
    LoginLogoutOrchestrator,
    FakeCredentials,
    FakeAttemptProtection,
    FakeCompletionPolicy,
    FakeSessionStore,
    FakeAccounts,
    FakeClock,
]:
    creds = credentials or FakeCredentials()
    service, store, accounts, clock = make_session_service()
    orchestrator = LoginLogoutOrchestrator(
        credentials=creds,  # type: ignore[arg-type]
        sessions=sessions or service,
        attempt_protection=attempt_protection or FakeAttemptProtection(),
        completion_policy=completion or FakeCompletionPolicy(),
        input_policy=LoginInputPolicy(
            max_username_characters=100,
            max_password_utf8_bytes=4096,
            max_source_key_characters=128,
        ),
    )
    return (
        orchestrator,
        creds,
        attempt_protection or orchestrator._attempt_protection,  # test-local inspection
        completion or orchestrator._completion_policy,  # test-local inspection
        store,
        accounts,
        clock,
    )


def test_login_success_uses_explicit_policies_and_returns_minimal_protected_result() -> None:
    protection = FakeAttemptProtection()
    completion = FakeCompletionPolicy()
    orchestrator, credentials, _, _, store, _, _ = make_orchestrator(
        attempt_protection=protection, completion=completion
    )
    login = LoginInput("fictional.admin", PASSWORD)

    result = orchestrator.login(login, trusted_source_key="test-source")
    raw_token = result.session_for_cookie_delivery().token_for_cookie_delivery()

    assert isinstance(result, LoginResult)
    assert result.user_id == USER_ID
    assert result.credential_version == 4
    assert result.rehash_recommended is False
    assert len(store.created) == 1
    assert credentials.calls == [("fictional.admin", PASSWORD)]
    assert [outcome for _, outcome in protection.outcomes] == [
        CredentialAttemptOutcome.SUCCEEDED
    ]
    assert completion.identities == [VerifiedCredential(USER_ID, 4, False)]
    assert raw_token not in repr(login)
    assert PASSWORD not in repr(login)
    assert raw_token not in repr(result)
    assert PASSWORD not in repr(result)
    assert "password_hash" not in repr(result)
    assert not hasattr(result, "roles")
    assert not hasattr(result, "permissions")
    with pytest.raises(TypeError):
        json.dumps(result)


def test_invalid_input_is_bounded_before_attempt_protection_or_credential_check() -> None:
    protection = FakeAttemptProtection()
    orchestrator, credentials, _, _, store, _, _ = make_orchestrator(
        attempt_protection=protection
    )

    for login in (
        LoginInput("", PASSWORD),
        LoginInput("x" * 101, PASSWORD),
        LoginInput("name", "é" * 2049),
    ):
        with pytest.raises(LoginRejected) as error:
            orchestrator.login(login)
        assert error.value.reason is LoginFailureReason.INVALID_INPUT

    assert not protection.checked
    assert not credentials.calls
    assert not store.created


def test_login_attempt_protection_denial_precedes_expensive_credential_verification() -> None:
    protection = FakeAttemptProtection()
    protection.decision = LoginAttemptDecision.DENY
    orchestrator, credentials, _, _, store, _, _ = make_orchestrator(
        attempt_protection=protection
    )

    with pytest.raises(LoginRejected) as error:
        orchestrator.login(LoginInput("fictional.admin", PASSWORD))

    assert error.value.reason is LoginFailureReason.ATTEMPT_BLOCKED
    assert credentials.calls == []
    assert not store.created


def test_login_attempt_protection_failure_fails_closed_before_password_verification() -> None:
    protection = FakeAttemptProtection()
    protection.check_error = RuntimeError("rate limiter private detail")
    orchestrator, credentials, _, _, store, _, _ = make_orchestrator(
        attempt_protection=protection
    )

    with pytest.raises(LoginUnavailable) as error:
        orchestrator.login(LoginInput("fictional.admin", PASSWORD))

    assert error.value.reason is LoginFailureReason.PROTECTION_UNAVAILABLE
    assert "private detail" not in str(error.value)
    assert error.value.__cause__ is None
    assert not credentials.calls
    assert not store.created


@pytest.mark.parametrize(
    "reason",
    [
        CredentialFailureReason.PASSWORD_REJECTED,
        CredentialFailureReason.UNKNOWN_USER,
        CredentialFailureReason.INELIGIBLE_USER,
        CredentialFailureReason.MISSING_CREDENTIAL,
    ],
)
def test_credential_denials_are_generic_and_never_issue_session(
    reason: CredentialFailureReason,
) -> None:
    protection = FakeAttemptProtection()
    credentials = FakeCredentials(CredentialRejected(reason))
    orchestrator, _, _, _, store, _, _ = make_orchestrator(
        credentials=credentials, attempt_protection=protection
    )

    with pytest.raises(LoginRejected) as error:
        orchestrator.login(LoginInput("fictional.admin", PASSWORD))

    assert error.value.reason is LoginFailureReason.CREDENTIALS_REJECTED
    assert str(error.value) == LoginRejected.public_message
    assert [outcome for _, outcome in protection.outcomes] == [
        CredentialAttemptOutcome.FAILED
    ]
    assert not store.created


def test_credential_infrastructure_failure_is_generic_and_does_not_issue() -> None:
    credentials = FakeCredentials(
        CredentialVerificationUnavailable(
            CredentialFailureReason.PASSWORD_PROVIDER_FAILURE
        )
    )
    orchestrator, _, protection, _, store, _, _ = make_orchestrator(credentials=credentials)

    with pytest.raises(LoginUnavailable) as error:
        orchestrator.login(LoginInput("fictional.admin", PASSWORD))

    assert error.value.reason is LoginFailureReason.CREDENTIAL_VERIFICATION_UNAVAILABLE
    assert protection.outcomes == [(protection.checked[0], None)]
    assert not store.created


def test_failed_credentials_release_attempt_permit_with_failed_outcome() -> None:
    protection = FakeAttemptProtection()
    credentials = FakeCredentials(
        CredentialRejected(CredentialFailureReason.PASSWORD_REJECTED)
    )
    orchestrator, *_ = make_orchestrator(
        credentials=credentials, attempt_protection=protection
    )

    with pytest.raises(LoginRejected):
        orchestrator.login(LoginInput("fictional.admin", PASSWORD))

    assert [outcome for _, outcome in protection.outcomes] == [
        CredentialAttemptOutcome.FAILED
    ]


def test_login_input_cannot_be_serialized_or_repr_leak_credentials() -> None:
    login_input = LoginInput("fictional.admin", PASSWORD)

    assert PASSWORD not in repr(login_input)
    assert "fictional.admin" not in repr(login_input)
    with pytest.raises(TypeError):
        json.dumps(login_input)


@pytest.mark.parametrize(
    ("decision", "reason"),
    [
        (
            AuthenticationCompletionDecision.INCOMPLETE,
            LoginFailureReason.AUTHENTICATION_INCOMPLETE,
        ),
        (
            AuthenticationCompletionDecision.DENY,
            LoginFailureReason.AUTHENTICATION_DENIED,
        ),
    ],
)
def test_incomplete_or_denied_authentication_completion_never_issues_session(
    decision: AuthenticationCompletionDecision,
    reason: LoginFailureReason,
) -> None:
    completion = FakeCompletionPolicy()
    completion.decision = decision
    orchestrator, credentials, _, _, store, _, _ = make_orchestrator(completion=completion)

    with pytest.raises(LoginRejected) as error:
        orchestrator.login(LoginInput("fictional.admin", PASSWORD))

    assert error.value.reason is reason
    assert credentials.calls
    assert not store.created


def test_authentication_completion_policy_failure_fails_closed() -> None:
    completion = FakeCompletionPolicy()
    completion.failure = RuntimeError("challenge verifier detail")
    orchestrator, _, _, _, store, _, _ = make_orchestrator(completion=completion)

    with pytest.raises(LoginUnavailable) as error:
        orchestrator.login(LoginInput("fictional.admin", PASSWORD))

    assert error.value.reason is LoginFailureReason.COMPLETION_POLICY_UNAVAILABLE
    assert "challenge verifier detail" not in str(error.value)
    assert error.value.__cause__ is None
    assert not store.created


def test_unknown_completion_policy_result_is_not_permissive() -> None:
    completion = FakeCompletionPolicy()
    completion.decision = True  # type: ignore[assignment]
    orchestrator, _, _, _, store, _, _ = make_orchestrator(completion=completion)

    with pytest.raises(LoginUnavailable):
        orchestrator.login(LoginInput("fictional.admin", PASSWORD))

    assert not store.created


def test_attempt_recording_failure_prevents_session_creation_after_password_check() -> None:
    protection = FakeAttemptProtection()
    protection.finish_error = RuntimeError("attempt store error")
    orchestrator, _, _, _, store, _, _ = make_orchestrator(
        attempt_protection=protection
    )

    with pytest.raises(LoginUnavailable) as error:
        orchestrator.login(LoginInput("fictional.admin", PASSWORD))

    assert error.value.reason is LoginFailureReason.PROTECTION_UNAVAILABLE
    assert not store.created


def test_stale_credential_or_deactivated_account_between_verification_and_issue_is_denied() -> None:
    for state in (
        CurrentAccountSessionState(USER_ID, "inactive", 4),
        CurrentAccountSessionState(USER_ID, "active", 5),
    ):
        accounts = FakeAccounts()
        accounts.states[USER_ID] = state
        service, store, _, _ = make_session_service(accounts=accounts)
        orchestrator, *_ = make_orchestrator(sessions=service)

        with pytest.raises(LoginRejected) as error:
            orchestrator.login(LoginInput("fictional.admin", PASSWORD))

        assert error.value.reason is LoginFailureReason.STALE_IDENTITY
        assert not store.created


def test_session_persistence_failure_returns_no_login_result_or_token() -> None:
    service, store, _, _ = make_session_service()
    store.failure_on = "create"
    orchestrator, *_ = make_orchestrator(sessions=service)

    with pytest.raises(LoginUnavailable) as error:
        orchestrator.login(LoginInput("fictional.admin", PASSWORD))

    assert error.value.reason is LoginFailureReason.SESSION_UNAVAILABLE
    assert error.value.__cause__ is None
    assert not store.created


def test_uncertain_session_commit_returns_no_token_and_documents_orphan_risk() -> None:
    service, store, _, _ = make_session_service()
    store.uncertain_create = True
    orchestrator, *_ = make_orchestrator(sessions=service)

    with pytest.raises(LoginUnavailable):
        orchestrator.login(LoginInput("fictional.admin", PASSWORD))

    # Fake simulates commit-then-network-failure: a persisted orphan may exist,
    # but no raw token or successful login result is returned to the caller.
    assert len(store.created) == 1


def test_rehash_recommendation_is_preserved_without_credential_changes() -> None:
    credentials = FakeCredentials(VerifiedCredential(USER_ID, 4, True))
    orchestrator, _, _, _, store, _, _ = make_orchestrator(credentials=credentials)

    result = orchestrator.login(LoginInput("fictional.admin", PASSWORD))

    assert result.rehash_recommended is True
    assert result.credential_version == 4
    assert len(store.created) == 1
    assert not hasattr(store.created[0], "password_hash")


def test_logout_revokes_only_current_session_and_is_repeatable() -> None:
    orchestrator, _, _, _, store, _, _ = make_orchestrator()
    first = orchestrator.login(LoginInput("fictional.admin", PASSWORD))
    second = orchestrator.login(LoginInput("fictional.admin", PASSWORD))
    first_token = first.session_for_cookie_delivery().token_for_cookie_delivery()
    second_token = second.session_for_cookie_delivery().token_for_cookie_delivery()

    logout = orchestrator.logout(first_token)

    assert logout.outcome is LogoutOutcome.REVOKED
    assert logout.clear_local_cookie is True
    assert orchestrator.logout(first_token).outcome is LogoutOutcome.ALREADY_REVOKED
    assert len(store.revocations) == 1
    assert not store.activity_updates
    assert not hasattr(orchestrator, "revoke_all_for_user")
    assert second.session_id != first.session_id
    assert len(store.by_digest) == 2
    assert store.by_digest[_digest_token(second_token)].revoked_at is None


@pytest.mark.parametrize(
    ("token", "outcome"),
    [
        ("invalid-token", LogoutOutcome.INVALID_TOKEN),
        (secrets.token_urlsafe(32), LogoutOutcome.SESSION_ABSENT),
    ],
)
def test_logout_invalid_and_absent_sessions_still_request_cookie_clear(
    token: str, outcome: LogoutOutcome
) -> None:
    orchestrator, _, _, _, store, _, _ = make_orchestrator()

    result = orchestrator.logout(token)

    assert result.outcome is outcome
    assert result.clear_local_cookie is True
    assert not store.activity_updates


def test_logout_expired_session_can_still_be_revoked() -> None:
    orchestrator, _, _, _, store, _, clock = make_orchestrator()
    login = orchestrator.login(LoginInput("fictional.admin", PASSWORD))
    token = login.session_for_cookie_delivery().token_for_cookie_delivery()
    clock.now = NOW + timedelta(hours=9)

    result = orchestrator.logout(token)

    assert result.outcome is LogoutOutcome.REVOKED
    assert store.revocations


def test_logout_repository_failure_is_uncertain_but_cookie_should_be_cleared() -> None:
    orchestrator, _, _, _, store, _, _ = make_orchestrator()
    login = orchestrator.login(LoginInput("fictional.admin", PASSWORD))
    token = login.session_for_cookie_delivery().token_for_cookie_delivery()
    store.failure_on = "revoke"

    result = orchestrator.logout(token)

    assert result.outcome is LogoutOutcome.REVOCATION_UNCERTAIN
    assert result.clear_local_cookie is True
    assert not store.revocations


def test_logout_commit_then_failure_is_not_reported_as_success() -> None:
    orchestrator, _, _, _, store, _, _ = make_orchestrator()
    login = orchestrator.login(LoginInput("fictional.admin", PASSWORD))
    token = login.session_for_cookie_delivery().token_for_cookie_delivery()
    store.uncertain_revoke = True

    result = orchestrator.logout(token)

    assert result.outcome is LogoutOutcome.REVOCATION_UNCERTAIN
    assert result.clear_local_cookie is True
    assert store.revocations


def test_fake_policy_protocols_receive_no_password_and_are_explicit() -> None:
    protection = FakeAttemptProtection()
    completion = FakeCompletionPolicy()
    orchestrator, _, _, _, _, _, _ = make_orchestrator(
        attempt_protection=protection, completion=completion
    )

    orchestrator.login(LoginInput("fictional.admin", PASSWORD), trusted_source_key="test-network")

    assert protection.checked[0].trusted_source_key == "test-network"
    assert PASSWORD not in repr(protection.checked[0])
    assert not hasattr(protection.checked[0], "password")
    assert completion.identities == [VerifiedCredential(USER_ID, 4, False)]


def test_end_to_end_offline_login_logout_with_real_argon2id_and_existing_services() -> None:
    from app.core.sessions import (
        SessionLifecycleService,
    )

    parameters = Argon2CostParameters(1024, 2, 1, 16, 32)
    limits = Argon2VerificationLimits(4096, 4, 2, 32, 64, 512, 4096)
    password_service = PasswordHashingService(
        Argon2idPasswordBackend(hash_parameters=parameters, verification_limits=limits)
    )
    account_hash = password_service.hash_password(PASSWORD)
    dummy_hash = password_service.hash_password("Fictional dummy password for login tests")

    class UserRepo:
        def find_by_canonical_username(self, canonical_username: str):
            if canonical_username == "fictional.admin":
                return [LoginUser(USER_ID, "fictional.admin", "active")]
            return []

    class CredentialRepo:
        def get_for_user(self, user_id: UUID):
            return PasswordCredentialRecord(user_id, account_hash, 4)

    credential_service = CredentialVerificationService(
        users=UserRepo(),  # type: ignore[arg-type]
        credentials=CredentialRepo(),  # type: ignore[arg-type]
        passwords=password_service,
        canonicalize_username=lambda value: value.casefold(),
        dummy_credential=DummyVerificationCredential(dummy_hash),
    )
    accounts = FakeAccounts()
    store = FakeSessionStore(accounts)
    session_service = SessionLifecycleService(
        sessions=store,
        accounts=accounts,
        policy=make_test_session_policy(),
        clock=FakeClock(),
    )
    orchestrator = LoginLogoutOrchestrator(
        credentials=credential_service,
        sessions=session_service,
        attempt_protection=FakeAttemptProtection(),
        completion_policy=FakeCompletionPolicy(),
        input_policy=LoginInputPolicy(
            max_username_characters=100,
            max_password_utf8_bytes=4096,
            max_source_key_characters=128,
        ),
    )

    login = orchestrator.login(LoginInput("FICTIONAL.ADMIN", PASSWORD))
    issued = login.session_for_cookie_delivery()
    token = issued.token_for_cookie_delivery()
    assert session_service.validate(token).user_id == USER_ID

    logout = orchestrator.logout(token)
    assert logout.outcome is LogoutOutcome.REVOKED
    assert logout.clear_local_cookie is True
    with pytest.raises(SessionRejected):
        session_service.validate(token)
    assert not store.activity_updates
