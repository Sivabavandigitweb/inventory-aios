import base64
import logging
from unittest.mock import Mock

import pytest
from argon2 import extract_parameters

from app.core.argon2_passwords import (
    Argon2CostParameters,
    Argon2idPasswordBackend,
    Argon2VerificationLimits,
)
from app.core.password_hashing import (
    InvalidStoredPasswordHash,
    PasswordHashingService,
    PasswordHashingUnavailable,
    PasswordInputError,
)


def make_limits(**overrides: int) -> Argon2VerificationLimits:
    values = {
        "max_memory_cost_kib": 4096,
        "max_time_cost": 4,
        "max_parallelism": 2,
        "max_salt_length": 32,
        "max_hash_length": 64,
        "max_encoded_hash_bytes": 512,
        "max_password_bytes": 4096,
    }
    values.update(overrides)
    return Argon2VerificationLimits(**values)


def make_backend(
    *,
    memory_cost_kib: int = 1024,
    time_cost: int = 2,
    parallelism: int = 1,
    salt_length: int = 16,
    hash_length: int = 32,
    limits: Argon2VerificationLimits | None = None,
) -> Argon2idPasswordBackend:
    return Argon2idPasswordBackend(
        hash_parameters=Argon2CostParameters(
            memory_cost_kib=memory_cost_kib,
            time_cost=time_cost,
            parallelism=parallelism,
            salt_length=salt_length,
            hash_length=hash_length,
        ),
        verification_limits=limits or make_limits(),
    )


def make_phc(
    *,
    algorithm: str = "argon2id",
    version: int = 19,
    memory_cost: int = 1024,
    time_cost: int = 2,
    parallelism: int = 1,
    salt_length: int = 16,
    hash_length: int = 32,
) -> str:
    salt = base64.b64encode(b"s" * salt_length).decode("ascii").rstrip("=")
    digest = base64.b64encode(b"h" * hash_length).decode("ascii").rstrip("=")
    return (
        f"${algorithm}$v={version}$m={memory_cost},t={time_cost},p={parallelism}"
        f"${salt}${digest}"
    )


def test_real_argon2id_hash_is_valid_and_verifies_only_the_matching_password() -> None:
    service = PasswordHashingService(make_backend())
    encoded_hash = service.hash_password("Fictional password for tests")

    assert encoded_hash.startswith("$argon2id$v=19$")
    assert service.verify_password("Fictional password for tests", encoded_hash) is True
    assert service.verify_password("different fictional password", encoded_hash) is False
    assert extract_parameters(encoded_hash).memory_cost == 1024


def test_real_hashes_use_distinct_random_salts() -> None:
    service = PasswordHashingService(make_backend())
    first = service.hash_password("same fictional password")
    second = service.hash_password("same fictional password")

    assert first != second
    assert first.split("$")[4] != second.split("$")[4]


def test_unicode_is_preserved_without_normalization() -> None:
    service = PasswordHashingService(make_backend())
    decomposed = "cafe\u0301-東京"
    composed = "caf\u00e9-東京"
    encoded_hash = service.hash_password(decomposed)

    assert service.verify_password(decomposed, encoded_hash) is True
    assert service.verify_password(composed, encoded_hash) is False


def test_long_password_is_not_truncated_within_explicit_input_limit() -> None:
    service = PasswordHashingService(make_backend())
    password = "long-passphrase-" * 100
    encoded_hash = service.hash_password(password)

    assert service.verify_password(password, encoded_hash) is True
    assert service.verify_password(password[:-1], encoded_hash) is False


def test_input_limit_is_explicit_and_rejects_without_truncation() -> None:
    limits = make_limits(max_password_bytes=64)
    service = PasswordHashingService(make_backend(limits=limits))
    password = "x" * 65

    with pytest.raises(PasswordInputError):
        service.hash_password(password)
    assert service.verify_password(password, make_phc()) is False


@pytest.mark.parametrize(
    "encoded_hash",
    [
        "not-a-phc-hash",
        make_phc(algorithm="argon2i"),
        make_phc(version=16),
        make_phc(memory_cost=4097),
        make_phc(time_cost=5),
        make_phc(parallelism=3),
        make_phc(salt_length=33),
        make_phc(hash_length=65),
    ],
    ids=["malformed", "unsupported-algorithm", "unsupported-version", "memory", "time", "parallelism", "salt", "tag"],
)
def test_unsafe_or_unsupported_hashes_are_rejected_before_verify(
    encoded_hash: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = make_backend()
    verify = Mock(side_effect=AssertionError("verify must not be called"))
    monkeypatch.setattr("app.core.argon2_passwords.PasswordHasher.verify", verify)

    with pytest.raises(InvalidStoredPasswordHash):
        backend.verify("fictional password", encoded_hash)

    verify.assert_not_called()


def test_encoded_hash_size_is_bounded_before_phc_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits = make_limits(max_encoded_hash_bytes=96)
    backend = make_backend(limits=limits)
    verify = Mock(side_effect=AssertionError("verify must not be called"))
    monkeypatch.setattr("app.core.argon2_passwords.PasswordHasher.verify", verify)
    oversized = make_phc() + ("x" * 97)

    with pytest.raises(InvalidStoredPasswordHash):
        backend.verify("fictional password", oversized)
    verify.assert_not_called()


def test_current_parameters_do_not_require_rehash_and_supported_older_hash_does() -> None:
    current_backend = make_backend(memory_cost_kib=2048, time_cost=2)
    service = PasswordHashingService(current_backend)
    current_hash = service.hash_password("fictional current password")
    assert service.needs_rehash(current_hash) is False

    old_backend = make_backend(memory_cost_kib=512, time_cost=1)
    old_hash = PasswordHashingService(old_backend).hash_password("fictional old password")
    assert service.verify_password("fictional old password", old_hash) is True
    assert service.needs_rehash(old_hash) is True


def test_unreasonable_hash_generation_configuration_is_rejected() -> None:
    with pytest.raises(ValueError, match="safety ceilings"):
        make_backend(memory_cost_kib=8192)


def test_unexpected_library_failures_are_generic_and_not_logged(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = make_backend()
    service = PasswordHashingService(backend)
    hashing = Mock(side_effect=RuntimeError("secret password/hash detail"))
    monkeypatch.setattr("app.core.argon2_passwords.PasswordHasher.hash", hashing)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(PasswordHashingUnavailable) as error:
            service.hash_password("fictional password")

    assert str(error.value) == "Password hashing service is unavailable."
    assert "secret password/hash detail" not in str(error.value)
    assert "secret password/hash detail" not in caplog.text


def test_needs_rehash_rejects_malformed_hash_without_leaking_it() -> None:
    service = PasswordHashingService(make_backend())
    marker = "not-a-valid-stored-hash"

    with pytest.raises(InvalidStoredPasswordHash) as error:
        service.needs_rehash(marker)

    assert marker not in str(error.value)
