"""Provider-neutral password hashing boundary; no production adapter is configured."""

from __future__ import annotations

from typing import Protocol


class InvalidStoredPasswordHash(ValueError):
    """The persisted encoding or its parameters cannot safely be verified."""

    def __init__(self) -> None:
        super().__init__("Stored password hash is invalid.")


class PasswordInputError(ValueError):
    """The supplied value is not a usable password string."""

    def __init__(self) -> None:
        super().__init__("Password input is invalid.")


class PasswordHashingUnavailable(RuntimeError):
    """The configured hashing provider failed; details are intentionally hidden."""

    def __init__(self) -> None:
        super().__init__("Password hashing service is unavailable.")


class PasswordHashBackend(Protocol):
    """Adapter contract for a maintained password-hashing library.

    Implementations must use a password-hashing algorithm with a library-generated
    random salt and return its encoded representation. They must reject malformed,
    unsupported, or excessive stored parameters before expensive verification.
    Password policy, account lookup, persistence, and login orchestration belong
    outside this boundary.
    """

    def hash(self, password: str) -> str: ...

    def verify(self, password: str, encoded_hash: str) -> bool: ...

    def needs_rehash(self, encoded_hash: str) -> bool: ...


class PasswordHashingService:
    """Safely delegate password operations without choosing a provider or policy."""

    def __init__(self, backend: PasswordHashBackend) -> None:
        self._backend = backend

    def hash_password(self, password: str) -> str:
        if not isinstance(password, str) or not password:
            raise PasswordInputError from None

        try:
            encoded_hash = self._backend.hash(password)
        except PasswordInputError:
            raise PasswordInputError from None
        except Exception:
            raise PasswordHashingUnavailable from None

        if not isinstance(encoded_hash, str) or not encoded_hash:
            raise PasswordHashingUnavailable from None
        return encoded_hash

    def verify_password(self, password: str, encoded_hash: str) -> bool:
        if not isinstance(password, str) or not isinstance(encoded_hash, str):
            return False
        if not password or not encoded_hash:
            return False

        try:
            result = self._backend.verify(password, encoded_hash)
        except InvalidStoredPasswordHash:
            return False
        except PasswordInputError:
            return False
        except Exception:
            raise PasswordHashingUnavailable from None

        if not isinstance(result, bool):
            raise PasswordHashingUnavailable from None
        return result

    def needs_rehash(self, encoded_hash: str) -> bool:
        if not isinstance(encoded_hash, str) or not encoded_hash:
            raise InvalidStoredPasswordHash from None

        try:
            result = self._backend.needs_rehash(encoded_hash)
        except InvalidStoredPasswordHash:
            raise InvalidStoredPasswordHash from None
        except Exception:
            raise PasswordHashingUnavailable from None

        if not isinstance(result, bool):
            raise PasswordHashingUnavailable from None
        return result
