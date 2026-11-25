"""Deterministic, deliberately narrow command fingerprinting; never logs inputs."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

_SCOPE = re.compile(r"^[A-Za-z0-9:/._-]{1,200}$")
_SENSITIVE = (
    "password", "passphrase", "secret", "token", "credential",
    "authorization", "apikey", "cookie", "sessionkey",
)
_MAX_DEPTH = 32
_MAX_BYTES = 1_000_000


class InvalidFingerprintInput(ValueError):
    """Safe error that never contains a request value or field name."""

    def __init__(self) -> None:
        super().__init__("Unsupported idempotency request data.")


def _canonical(value: object, active: set[int], depth: int) -> object:
    if depth > _MAX_DEPTH:
        raise InvalidFingerprintInput()
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, str):
        return ["str", unicodedata.normalize("NFC", value)]
    if isinstance(value, int):
        return ["int", str(value)]
    if isinstance(value, Decimal):
        if not value.is_finite() or len(value.as_tuple().digits) > 1000 or abs(value.adjusted()) > 10000:
            raise InvalidFingerprintInput()
        if not value:
            return ["decimal", "0"]
        decimal_tuple = value.as_tuple()
        digits = "".join(str(digit) for digit in decimal_tuple.digits)
        exponent = decimal_tuple.exponent
        while digits.endswith("0") and len(digits) > 1:
            digits = digits[:-1]
            exponent += 1
        return ["decimal", "-" if decimal_tuple.sign else "+", digits, exponent]
    if isinstance(value, UUID):
        return ["uuid", str(value)]
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise InvalidFingerprintInput()
        utc = value.astimezone(timezone.utc)
        return ["datetime", utc.isoformat(timespec="microseconds")]
    if isinstance(value, date):
        return ["date", value.isoformat()]
    if not isinstance(value, (Mapping, list, tuple)):
        raise InvalidFingerprintInput()
    identity = id(value)
    if identity in active:
        raise InvalidFingerprintInput()
    active.add(identity)
    try:
        if isinstance(value, Mapping):
            fields: dict[str, object] = {}
            for raw_key, item in value.items():
                if not isinstance(raw_key, str):
                    raise InvalidFingerprintInput()
                key = unicodedata.normalize("NFC", raw_key)
                compact = re.sub(r"[^a-z0-9]", "", key.casefold())
                if key in fields or any(term in compact for term in _SENSITIVE):
                    raise InvalidFingerprintInput()
                fields[key] = _canonical(item, active, depth + 1)
            return ["object", [[key, fields[key]] for key in sorted(fields)]]
        return ["array", [_canonical(item, active, depth + 1) for item in value]]
    finally:
        active.remove(identity)


def fingerprint_request(operation_scope: str, command: Mapping[str, object]) -> str:
    """Hash validated command data under a versioned operation scope.

    SHA-256 provides equality, not confidentiality. Do not pass secrets or expose hashes.
    """
    if not isinstance(operation_scope, str) or not _SCOPE.fullmatch(operation_scope):
        raise InvalidFingerprintInput()
    if not isinstance(command, Mapping):
        raise InvalidFingerprintInput()
    canonical = ["inventory-aios-idempotency-v1", operation_scope, _canonical(command, set(), 0)]
    try:
        encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (UnicodeError, ValueError, OverflowError):
        raise InvalidFingerprintInput() from None
    if len(encoded) > _MAX_BYTES:
        raise InvalidFingerprintInput()
    return hashlib.sha256(encoded).hexdigest()
