from __future__ import annotations

from dataclasses import FrozenInstanceError
from uuid import UUID

import pytest

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
from app.core.password_hashing import (
    InvalidStoredPasswordHash,
    PasswordHashingService,
    PasswordHashingUnavailable,
)

USER_ID = UUID("10000000-0000-4000-8000-000000000001")
OTHER_USER_ID = UUID("20000000-0000-4000-8000-000000000002")
PASSWORD = "Fictional test passphrase"
DUMMY_HASH = "fake-argon2id-dummy-test-hash"


class FakeUserRepository:
    def __init__(self, matches: object = ()) -> None:
        self.matches = matches
        self.looked_up: list[str] = []
        self.failure: Exception | None = None

    def find_by_canonical_username(self, canonical_username: str):
        self.looked_up.append(canonical_username)
        if self.failure is not None:
            raise self.failure
        return self.matches


class FakeCredentialRepository:
    def __init__(self, credential: PasswordCredentialRecord | None) -> None:
        self.credential = credential
        self.requested_users: list[UUID] = []
        self.failure: Exception | None = None

    def get_for_user(self, user_id: UUID):
        self.requested_users.append(user_id)
        if self.failure is not None:
            raise self.failure
        return self.credential


class FakePasswordService:
    def __init__(self) -> None:
        self.passwords_by_hash: dict[str, str] = {"credential-hash": PASSWORD}
        self.rehash_by_hash: dict[str, bool] = {"credential-hash": False}
        self.verify_calls: list[tuple[str, str]] = []
        self.rehash_calls: list[str] = []
        self.invalid_hashes: set[str] = set()
        self.fail_verify = False
        self.fail_rehash = False

    def verify_password(self, password: str, encoded_hash: str) -> bool:
        self.verify_calls.append((password, encoded_hash))
        if self.fail_verify:
            raise PasswordHashingUnavailable
        return self.passwords_by_hash.get(encoded_hash) == password

    def needs_rehash(self, encoded_hash: str) -> bool:
        self.rehash_calls.append(encoded_hash)
        if self.fail_rehash:
            raise PasswordHashingUnavailable
        if encoded_hash in self.invalid_hashes:
            raise InvalidStoredPasswordHash
        return self.rehash_by_hash.get(encoded_hash, False)


def make_service(
    *,
    users: FakeUserRepository | None = None,
    credentials: FakeCredentialRepository | None = None,
    passwords: FakePasswordService | None = None,
    canonicalize=lambda value: value.casefold(),
) -> tuple[CredentialVerificationService, FakeUserRepository, FakeCredentialRepository, FakePasswordService]:
    user_repository = users or FakeUserRepository(
        [LoginUser(user_id=USER_ID, username="Admin.Example", status="active")]
    )
    credential_repository = credentials or FakeCredentialRepository(
        PasswordCredentialRecord(
            user_id=USER_ID,
            password_hash="credential-hash",
            credential_version=3,
        )
    )
    password_service = passwords or FakePasswordService()
    service = CredentialVerificationService(
        users=user_repository,
        credentials=credential_repository,
        passwords=password_service,  # type: ignore[arg-type]
        canonicalize_username=canonicalize,
        dummy_credential=DummyVerificationCredential(password_hash=DUMMY_HASH),
    )
    return service, user_repository, credential_repository, password_service


def test_active_user_with_correct_password_returns_only_minimal_verified_identity() -> None:
    service, users, credentials, passwords = make_service()

    result = service.verify("ADMIN.EXAMPLE", PASSWORD)

    assert result == VerifiedCredential(USER_ID, 3, False)
    assert users.looked_up == ["admin.example"]
    assert credentials.requested_users == [USER_ID]
    assert passwords.rehash_calls == ["credential-hash"]
    assert not hasattr(result, "roles")
    assert not hasattr(result, "permissions")
    assert not hasattr(result, "password_hash")
    assert not hasattr(result, "password")


def test_successful_result_is_immutable_and_does_not_grant_access() -> None:
    service, *_ = make_service()
    result = service.verify("admin.example", PASSWORD)

    with pytest.raises(FrozenInstanceError):
        result.credential_version = 4  # type: ignore[misc]
    assert result.user_id == USER_ID
    assert result.credential_version == 3


def test_active_user_with_incorrect_password_is_rejected_generically() -> None:
    service, _, _, passwords = make_service()

    with pytest.raises(CredentialRejected) as error:
        service.verify("admin.example", "wrong fictional password")

    assert error.value.reason is CredentialFailureReason.PASSWORD_REJECTED
    assert str(error.value) == "Credentials are invalid."
    assert passwords.verify_calls == [("wrong fictional password", "credential-hash")]
    assert passwords.verify_calls[-1][1] != DUMMY_HASH


def test_unknown_username_uses_dummy_hash_and_cannot_authenticate() -> None:
    users = FakeUserRepository([])
    passwords = FakePasswordService()
    passwords.passwords_by_hash[DUMMY_HASH] = PASSWORD
    service, _, _, _ = make_service(users=users, passwords=passwords)

    with pytest.raises(CredentialRejected) as error:
        service.verify("missing.user", PASSWORD)

    assert error.value.reason is CredentialFailureReason.UNKNOWN_USER
    assert passwords.verify_calls == [(PASSWORD, DUMMY_HASH)]
    assert str(error.value) == "Credentials are invalid."


@pytest.mark.parametrize("status", ["inactive", "disabled", "pending", "", None])
def test_inactive_or_unsupported_account_status_is_denied(status: object) -> None:
    users = FakeUserRepository([LoginUser(USER_ID, "admin.example", status)])
    service, _, credentials, passwords = make_service(users=users)

    with pytest.raises(CredentialRejected) as error:
        service.verify("admin.example", PASSWORD)

    assert error.value.reason is CredentialFailureReason.INELIGIBLE_USER
    assert credentials.requested_users == []
    assert passwords.verify_calls == [(PASSWORD, DUMMY_HASH)]


def test_missing_password_credential_is_denied_after_dummy_verification() -> None:
    credentials = FakeCredentialRepository(None)
    service, _, _, passwords = make_service(credentials=credentials)

    with pytest.raises(CredentialRejected) as error:
        service.verify("admin.example", PASSWORD)

    assert error.value.reason is CredentialFailureReason.MISSING_CREDENTIAL
    assert passwords.verify_calls == [(PASSWORD, DUMMY_HASH)]


def test_mismatched_user_and_credential_ids_fail_closed() -> None:
    credentials = FakeCredentialRepository(
        PasswordCredentialRecord(OTHER_USER_ID, "credential-hash", 3)
    )
    service, _, _, passwords = make_service(credentials=credentials)

    with pytest.raises(CredentialVerificationUnavailable) as error:
        service.verify("admin.example", PASSWORD)

    assert error.value.reason is CredentialFailureReason.INCONSISTENT_DATA
    assert str(error.value) == "Credential verification is temporarily unavailable."
    assert passwords.verify_calls == [(PASSWORD, DUMMY_HASH)]


@pytest.mark.parametrize("version", [0, -1, True, "3"])
def test_invalid_credential_version_fails_closed(version: object) -> None:
    credentials = FakeCredentialRepository(
        PasswordCredentialRecord(USER_ID, "credential-hash", version)  # type: ignore[arg-type]
    )
    service, *_ = make_service(credentials=credentials)

    with pytest.raises(CredentialVerificationUnavailable) as error:
        service.verify("admin.example", PASSWORD)

    assert error.value.reason is CredentialFailureReason.INCONSISTENT_DATA


def test_ambiguous_identity_lookup_fails_closed_and_runs_dummy_verification() -> None:
    users = FakeUserRepository(
        [
            LoginUser(USER_ID, "admin.example", "active"),
            LoginUser(OTHER_USER_ID, "admin.example", "active"),
        ]
    )
    service, _, credentials, passwords = make_service(users=users)

    with pytest.raises(CredentialVerificationUnavailable) as error:
        service.verify("admin.example", PASSWORD)

    assert error.value.reason is CredentialFailureReason.INCONSISTENT_DATA
    assert credentials.requested_users == []
    assert passwords.verify_calls == [(PASSWORD, DUMMY_HASH)]


def test_inconsistent_username_result_is_rejected_without_exposing_identity() -> None:
    users = FakeUserRepository([LoginUser(USER_ID, "different.user", "active")])
    service, *_ = make_service(users=users)

    with pytest.raises(CredentialVerificationUnavailable) as error:
        service.verify("admin.example", PASSWORD)

    assert error.value.reason is CredentialFailureReason.INCONSISTENT_DATA
    assert "different.user" not in str(error.value)


def test_malformed_stored_hash_is_rejected_and_dummy_work_is_attempted() -> None:
    credentials = FakeCredentialRepository(PasswordCredentialRecord(USER_ID, "bad-hash", 3))
    service, _, _, passwords = make_service(credentials=credentials)
    passwords.invalid_hashes.add("bad-hash")

    with pytest.raises(CredentialVerificationUnavailable) as error:
        service.verify("admin.example", PASSWORD)

    assert error.value.reason is CredentialFailureReason.INCONSISTENT_DATA
    assert passwords.verify_calls == [(PASSWORD, DUMMY_HASH)]


def test_real_argon2_adapter_rejects_unsupported_hashes_before_acceptance() -> None:
    from argon2 import PasswordHasher
    from argon2.low_level import Type

    from app.core.argon2_passwords import (
        Argon2CostParameters,
        Argon2idPasswordBackend,
        Argon2VerificationLimits,
    )

    backend = Argon2idPasswordBackend(
        hash_parameters=Argon2CostParameters(1024, 2, 1, 16, 32),
        verification_limits=Argon2VerificationLimits(4096, 4, 2, 32, 64, 512, 4096),
    )
    actual_service = PasswordHashingService(backend)
    dummy_hash = actual_service.hash_password("fictional dummy-only password")
    unsupported_hash = PasswordHasher(type=Type.I).hash("fictional account password")
    credentials = FakeCredentialRepository(
        PasswordCredentialRecord(USER_ID, unsupported_hash, 3)
    )
    service = CredentialVerificationService(
        users=FakeUserRepository([LoginUser(USER_ID, "admin.example", "active")]),
        credentials=credentials,
        passwords=actual_service,
        canonicalize_username=lambda value: value.casefold(),
        dummy_credential=DummyVerificationCredential(dummy_hash),
    )

    with pytest.raises(CredentialVerificationUnavailable) as error:
        service.verify("admin.example", "fictional account password")

    assert error.value.reason is CredentialFailureReason.INCONSISTENT_DATA


def test_real_argon2_adapter_rejects_excessive_hash_cost_before_acceptance() -> None:
    from app.core.argon2_passwords import (
        Argon2CostParameters,
        Argon2idPasswordBackend,
        Argon2VerificationLimits,
    )

    backend = Argon2idPasswordBackend(
        hash_parameters=Argon2CostParameters(1024, 2, 1, 16, 32),
        verification_limits=Argon2VerificationLimits(4096, 4, 2, 32, 64, 512, 4096),
    )
    actual_service = PasswordHashingService(backend)
    dummy_hash = actual_service.hash_password("fictional dummy-only password")
    excessive_hash = (
        "$argon2id$v=19$m=4097,t=2,p=1$" "c2FsdHNhbHRzYWx0c2FsdA$" "aGFzaGhhc2hoYXNoaGFzaGhhc2hoYXNoaGFzaGg"
    )
    credentials = FakeCredentialRepository(PasswordCredentialRecord(USER_ID, excessive_hash, 3))
    service = CredentialVerificationService(
        users=FakeUserRepository([LoginUser(USER_ID, "admin.example", "active")]),
        credentials=credentials,
        passwords=actual_service,
        canonicalize_username=lambda value: value.casefold(),
        dummy_credential=DummyVerificationCredential(dummy_hash),
    )

    with pytest.raises(CredentialVerificationUnavailable) as error:
        service.verify("admin.example", "fictional account password")

    assert error.value.reason is CredentialFailureReason.INCONSISTENT_DATA


def test_username_repository_failure_is_sanitized_and_chaining_is_removed() -> None:
    users = FakeUserRepository()
    users.failure = RuntimeError("private database detail with fictional secret")
    service, *_ = make_service(users=users)

    with pytest.raises(CredentialVerificationUnavailable) as error:
        service.verify("admin.example", PASSWORD)

    assert error.value.reason is CredentialFailureReason.USER_REPOSITORY_FAILURE
    assert "private database detail" not in str(error.value)
    assert error.value.__cause__ is None


def test_credential_repository_failure_is_sanitized() -> None:
    credentials = FakeCredentialRepository(None)
    credentials.failure = RuntimeError("credential hash and SQL detail")
    service, *_ = make_service(credentials=credentials)

    with pytest.raises(CredentialVerificationUnavailable) as error:
        service.verify("admin.example", PASSWORD)

    assert error.value.reason is CredentialFailureReason.CREDENTIAL_REPOSITORY_FAILURE
    assert "credential hash" not in str(error.value)
    assert error.value.__cause__ is None


def test_password_provider_failure_is_sanitized() -> None:
    passwords = FakePasswordService()
    passwords.fail_verify = True
    service, *_ = make_service(passwords=passwords)

    with pytest.raises(CredentialVerificationUnavailable) as error:
        service.verify("admin.example", PASSWORD)

    assert error.value.reason is CredentialFailureReason.PASSWORD_PROVIDER_FAILURE
    assert str(error.value) == "Credential verification is temporarily unavailable."
    assert error.value.__cause__ is None


def test_unknown_inactive_missing_and_wrong_password_failures_share_public_message() -> None:
    cases = []
    cases.append(make_service(users=FakeUserRepository([]))[0])
    cases.append(
        make_service(
            users=FakeUserRepository([LoginUser(USER_ID, "admin.example", "inactive")])
        )[0]
    )
    cases.append(make_service(credentials=FakeCredentialRepository(None))[0])
    cases.append(make_service()[0])
    messages = []

    for index, service in enumerate(cases):
        candidate = "incorrect fictional password" if index == 3 else PASSWORD
        with pytest.raises(CredentialRejected) as error:
            service.verify("admin.example", candidate)
        messages.append(str(error.value))

    assert messages == ["Credentials are invalid."] * 4


def test_dummy_match_is_never_returned_as_a_verified_identity() -> None:
    users = FakeUserRepository([])
    passwords = FakePasswordService()
    passwords.passwords_by_hash[DUMMY_HASH] = PASSWORD
    service, *_ = make_service(users=users, passwords=passwords)

    with pytest.raises(CredentialRejected):
        service.verify("not-an-account", PASSWORD)


def test_rehash_recommendation_is_returned_without_persisting_or_changing_version() -> None:
    passwords = FakePasswordService()
    passwords.rehash_by_hash["credential-hash"] = True
    credentials = FakeCredentialRepository(
        PasswordCredentialRecord(USER_ID, "credential-hash", 7)
    )
    service, _, _, _ = make_service(credentials=credentials, passwords=passwords)

    result = service.verify("admin.example", PASSWORD)

    assert result.rehash_recommended is True
    assert result.credential_version == 7
    assert credentials.credential.credential_version == 7  # type: ignore[union-attr]


def test_identity_and_credential_representations_redact_username_and_hash() -> None:
    identity = LoginUser(USER_ID, "private.username", "active")
    credential = PasswordCredentialRecord(USER_ID, "sensitive-phc-hash", 2)
    dummy = DummyVerificationCredential("dummy-phc-hash")

    assert "private.username" not in repr(identity)
    assert "sensitive-phc-hash" not in repr(credential)
    assert "dummy-phc-hash" not in repr(dummy)


def test_canonicalizer_failure_is_rejected_without_leaking_details() -> None:
    def failed_canonicalizer(_: str) -> str:
        raise RuntimeError("normalization private detail")

    service, users, _, passwords = make_service(canonicalize=failed_canonicalizer)

    with pytest.raises(CredentialRejected) as error:
        service.verify("fictional.username", PASSWORD)

    assert error.value.reason is CredentialFailureReason.INVALID_INPUT
    assert "normalization private detail" not in str(error.value)
    assert users.looked_up == []
    assert passwords.verify_calls == [(PASSWORD, DUMMY_HASH)]


def test_user_repository_contract_rejects_non_sequence_result() -> None:
    service, *_ = make_service(users=FakeUserRepository("not-a-sequence"))

    with pytest.raises(CredentialVerificationUnavailable) as error:
        service.verify("admin.example", PASSWORD)

    assert error.value.reason is CredentialFailureReason.INCONSISTENT_DATA


def test_missing_non_string_and_empty_inputs_never_reach_identity_lookup() -> None:
    service, users, _, _ = make_service()

    for username, password in [("", PASSWORD), ("admin.example", ""), (None, PASSWORD)]:
        with pytest.raises(CredentialRejected):
            service.verify(username, password)  # type: ignore[arg-type]

    assert users.looked_up == []
