import logging

import pytest

from app.core.password_hashing import (
    InvalidStoredPasswordHash,
    PasswordHashingService,
    PasswordHashingUnavailable,
    PasswordInputError,
)


class FakePasswordBackend:
    def __init__(self) -> None:
        self.hash_result: object = "fake-phc-encoding"
        self.verify_result: object = True
        self.rehash_result: object = False
        self.hash_error: Exception | None = None
        self.verify_error: Exception | None = None
        self.rehash_error: Exception | None = None
        self.seen_password: str | None = None
        self.seen_hash: str | None = None

    def hash(self, password: str) -> str:
        self.seen_password = password
        if self.hash_error:
            raise self.hash_error
        return self.hash_result  # type: ignore[return-value]

    def verify(self, password: str, encoded_hash: str) -> bool:
        self.seen_password = password
        self.seen_hash = encoded_hash
        if self.verify_error:
            raise self.verify_error
        return self.verify_result  # type: ignore[return-value]

    def needs_rehash(self, encoded_hash: str) -> bool:
        self.seen_hash = encoded_hash
        if self.rehash_error:
            raise self.rehash_error
        return self.rehash_result  # type: ignore[return-value]


def test_hash_operation_passes_exact_text_without_normalizing_or_truncating() -> None:
    backend = FakePasswordBackend()
    service = PasswordHashingService(backend)
    password = "cafe\u0301 with spaces " + ("long-" * 1000)

    assert service.hash_password(password) == "fake-phc-encoding"
    assert backend.seen_password == password


def test_creation_policy_is_not_embedded_in_hash_service() -> None:
    backend = FakePasswordBackend()
    service = PasswordHashingService(backend)

    assert service.hash_password("short") == "fake-phc-encoding"
    assert backend.seen_password == "short"


def test_empty_and_non_text_passwords_are_rejected_for_hashing() -> None:
    service = PasswordHashingService(FakePasswordBackend())

    with pytest.raises(PasswordInputError):
        service.hash_password("")
    with pytest.raises(PasswordInputError):
        service.hash_password(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(("backend_result", "expected"), [(True, True), (False, False)])
def test_verification_returns_backend_match_result(backend_result: bool, expected: bool) -> None:
    backend = FakePasswordBackend()
    backend.verify_result = backend_result

    assert PasswordHashingService(backend).verify_password("fictional", "fake-hash") is expected


def test_verification_rejects_empty_inputs_and_invalid_stored_hash() -> None:
    backend = FakePasswordBackend()
    service = PasswordHashingService(backend)

    assert service.verify_password("", "fake-hash") is False
    assert service.verify_password("fictional", "") is False
    assert service.verify_password("fictional", None) is False  # type: ignore[arg-type]

    backend.verify_error = InvalidStoredPasswordHash()
    assert service.verify_password("fictional", "unsupported-or-malformed") is False


def test_malformed_or_excessive_hash_parameters_fail_as_invalid_credentials() -> None:
    backend = FakePasswordBackend()
    service = PasswordHashingService(backend)
    for reason in ("malformed", "unsupported algorithm", "excessive parameters"):
        backend.verify_error = InvalidStoredPasswordHash()
        assert service.verify_password("fictional", reason) is False

    backend.rehash_error = InvalidStoredPasswordHash()
    with pytest.raises(InvalidStoredPasswordHash) as error:
        service.needs_rehash("untrusted-stored-hash")
    assert str(error.value) == "Stored password hash is invalid."
    assert "untrusted-stored-hash" not in str(error.value)


def test_rehash_detection_is_delegated_to_the_backend() -> None:
    backend = FakePasswordBackend()
    service = PasswordHashingService(backend)

    assert service.needs_rehash("encoded-hash") is False
    backend.rehash_result = True
    assert service.needs_rehash("encoded-hash") is True
    assert backend.seen_hash == "encoded-hash"


@pytest.mark.parametrize("operation", ["hash", "verify", "rehash"])
def test_provider_failures_are_sanitized(operation: str, caplog: pytest.LogCaptureFixture) -> None:
    backend = FakePasswordBackend()
    service = PasswordHashingService(backend)
    sensitive_detail = "password=FICTIONAL-CREDENTIAL hash=FICTIONAL-HASH"
    setattr(backend, f"{operation}_error", RuntimeError(sensitive_detail))

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(PasswordHashingUnavailable) as error:
            if operation == "hash":
                service.hash_password("FICTIONAL-CREDENTIAL")
            elif operation == "verify":
                service.verify_password("FICTIONAL-CREDENTIAL", "FICTIONAL-HASH")
            else:
                service.needs_rehash("FICTIONAL-HASH")

    assert str(error.value) == "Password hashing service is unavailable."
    assert sensitive_detail not in str(error.value)
    assert sensitive_detail not in caplog.text


def test_non_boolean_provider_results_fail_closed() -> None:
    backend = FakePasswordBackend()
    backend.verify_result = "yes"
    service = PasswordHashingService(backend)

    with pytest.raises(PasswordHashingUnavailable):
        service.verify_password("fictional", "fake-hash")


def test_hashing_service_does_not_log_passwords_or_encoded_hashes(caplog: pytest.LogCaptureFixture) -> None:
    backend = FakePasswordBackend()
    backend.hash_result = "FICTIONAL-ENCODED-HASH"
    service = PasswordHashingService(backend)

    with caplog.at_level(logging.DEBUG):
        service.hash_password("FICTIONAL-PASSWORD")

    assert "FICTIONAL-PASSWORD" not in caplog.text
    assert "FICTIONAL-ENCODED-HASH" not in caplog.text
