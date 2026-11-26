"""Bounded Argon2id adapter for the provider-neutral password service."""

from __future__ import annotations

from dataclasses import dataclass

from argon2 import PasswordHasher, extract_parameters
from argon2.exceptions import (
    HashingError,
    InvalidHashError,
    UnsupportedParametersError,
    VerificationError,
    VerifyMismatchError,
)
from argon2.low_level import ARGON2_VERSION, Type

from app.core.password_hashing import (
    InvalidStoredPasswordHash,
    PasswordHashingUnavailable,
    PasswordInputError,
)


@dataclass(frozen=True)
class Argon2CostParameters:
    """Explicit parameters used only when generating new hashes."""

    memory_cost_kib: int
    time_cost: int
    parallelism: int
    salt_length: int
    hash_length: int

    def __post_init__(self) -> None:
        values = (
            self.memory_cost_kib,
            self.time_cost,
            self.parallelism,
            self.salt_length,
            self.hash_length,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("Argon2 parameters must be positive integers.")
        if self.memory_cost_kib < 8 * self.parallelism:
            raise ValueError("Argon2 memory cost is below the minimum for its parallelism.")
        if self.salt_length < 8 or self.hash_length < 4:
            raise ValueError("Argon2 salt or hash length is below the supported minimum.")


@dataclass(frozen=True)
class Argon2VerificationLimits:
    """Explicit resource-safety ceilings for untrusted encoded hashes and input."""

    max_memory_cost_kib: int
    max_time_cost: int
    max_parallelism: int
    max_salt_length: int
    max_hash_length: int
    max_encoded_hash_bytes: int
    max_password_bytes: int

    def __post_init__(self) -> None:
        values = (
            self.max_memory_cost_kib,
            self.max_time_cost,
            self.max_parallelism,
            self.max_salt_length,
            self.max_hash_length,
            self.max_encoded_hash_bytes,
            self.max_password_bytes,
        )
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("Argon2 verification limits must be positive integers.")
        if self.max_memory_cost_kib < 8 * self.max_parallelism:
            raise ValueError("Argon2 memory ceiling is below its parallelism minimum.")
        if self.max_salt_length < 8 or self.max_hash_length < 4:
            raise ValueError("Argon2 salt or hash ceiling is below the supported minimum.")


class Argon2idPasswordBackend:
    """An explicitly configured Argon2id provider with pre-verification bounds.

    No parameter defaults are supplied intentionally. Callers must provide both
    hash-generation costs and independent verification/resource ceilings.
    """

    def __init__(
        self,
        *,
        hash_parameters: Argon2CostParameters,
        verification_limits: Argon2VerificationLimits,
    ) -> None:
        self._limits = verification_limits
        self._validate_cost_parameters(hash_parameters)
        self._hasher = PasswordHasher(
            time_cost=hash_parameters.time_cost,
            memory_cost=hash_parameters.memory_cost_kib,
            parallelism=hash_parameters.parallelism,
            hash_len=hash_parameters.hash_length,
            salt_len=hash_parameters.salt_length,
            type=Type.ID,
        )

    def hash(self, password: str) -> str:
        self._validate_password(password)
        try:
            encoded_hash = self._hasher.hash(password)
        except (HashingError, UnsupportedParametersError):
            raise PasswordHashingUnavailable from None
        except Exception:
            raise PasswordHashingUnavailable from None

        self._validate_encoded_hash(encoded_hash)
        return encoded_hash

    def verify(self, password: str, encoded_hash: str) -> bool:
        self._validate_password(password)
        self._validate_encoded_hash(encoded_hash)
        try:
            return self._hasher.verify(encoded_hash, password)
        except VerifyMismatchError:
            return False
        except InvalidHashError:
            raise InvalidStoredPasswordHash from None
        except (VerificationError, UnsupportedParametersError):
            raise PasswordHashingUnavailable from None
        except Exception:
            raise PasswordHashingUnavailable from None

    def needs_rehash(self, encoded_hash: str) -> bool:
        self._validate_encoded_hash(encoded_hash)
        try:
            return self._hasher.check_needs_rehash(encoded_hash)
        except InvalidHashError:
            raise InvalidStoredPasswordHash from None
        except (VerificationError, UnsupportedParametersError):
            raise PasswordHashingUnavailable from None
        except Exception:
            raise PasswordHashingUnavailable from None

    def _validate_cost_parameters(self, parameters: Argon2CostParameters) -> None:
        if (
            parameters.memory_cost_kib > self._limits.max_memory_cost_kib
            or parameters.time_cost > self._limits.max_time_cost
            or parameters.parallelism > self._limits.max_parallelism
            or parameters.salt_length > self._limits.max_salt_length
            or parameters.hash_length > self._limits.max_hash_length
        ):
            raise ValueError("Argon2 generation parameters exceed configured safety ceilings.")

    def _validate_password(self, password: str) -> None:
        if not isinstance(password, str) or not password:
            raise PasswordInputError from None
        try:
            encoded = password.encode("utf-8")
        except UnicodeEncodeError:
            raise PasswordInputError from None
        if len(encoded) > self._limits.max_password_bytes:
            raise PasswordInputError from None

    def _validate_encoded_hash(self, encoded_hash: str) -> None:
        if not isinstance(encoded_hash, str) or not encoded_hash:
            raise InvalidStoredPasswordHash from None
        try:
            encoded_bytes = encoded_hash.encode("ascii")
        except UnicodeEncodeError:
            raise InvalidStoredPasswordHash from None
        if len(encoded_bytes) > self._limits.max_encoded_hash_bytes:
            raise InvalidStoredPasswordHash from None

        try:
            parameters = extract_parameters(encoded_hash)
        except (InvalidHashError, ValueError, TypeError):
            raise InvalidStoredPasswordHash from None
        except Exception:
            raise PasswordHashingUnavailable from None

        if (
            parameters.type is not Type.ID
            or parameters.version != ARGON2_VERSION
            or parameters.parallelism < 1
            or parameters.memory_cost < 8 * parameters.parallelism
            or parameters.time_cost < 1
            or parameters.salt_len < 8
            or parameters.hash_len < 4
            or parameters.memory_cost > self._limits.max_memory_cost_kib
            or parameters.time_cost > self._limits.max_time_cost
            or parameters.parallelism > self._limits.max_parallelism
            or parameters.salt_len > self._limits.max_salt_length
            or parameters.hash_len > self._limits.max_hash_length
        ):
            raise InvalidStoredPasswordHash from None
