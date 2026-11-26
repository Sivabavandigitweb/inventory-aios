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
