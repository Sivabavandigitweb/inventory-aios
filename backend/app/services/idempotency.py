"""Pure replay decisions; persistence and concurrency are deferred to a tested command runner."""

from __future__ import annotations

import hmac
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.core.authentication import Principal
from app.core.errors import AppError

_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_SCOPE = re.compile(r"^[A-Za-z0-9:/._-]{1,200}$")
_KEY = re.compile(r"^[A-Za-z0-9._~-]{1,200}$")


@dataclass(frozen=True)
class StoredRequest:
    principal_id: UUID
    operation_scope: str
    idempotency_key: str
    request_fingerprint: str
    status: Literal["processing", "succeeded"]
    response_status: int | None = None
    resource_type: str | None = None
    resource_id: UUID | None = None


@dataclass(frozen=True)
class RequestDecision:
    kind: Literal["execute", "replay"]
    response_status: int | None = None
    resource_type: str | None = None
    resource_id: UUID | None = None


OperationAuthorization = Callable[[Principal, str], None]
ResultAuthorization = Callable[[Principal, str | None, UUID | None], None]


def decide_request(
    *,
    principal: Principal,
    operation_scope: str,
    idempotency_key: str,
    request_fingerprint: str,
    existing: StoredRequest | None,
    authorize_operation: OperationAuthorization,
    authorize_result: ResultAuthorization,
) -> RequestDecision:
    """Decide from a caller-provided snapshot after fresh authorization checks.

    A future command runner must load a scoped row in the caller's transaction and
    enforce uniqueness/locking. This function performs no I/O or transaction control.
    """
    if (
        not isinstance(principal, Principal)
        or not isinstance(principal.user_id, UUID)
        or not isinstance(operation_scope, str)
        or not _SCOPE.fullmatch(operation_scope)
        or not isinstance(idempotency_key, str)
        or not _KEY.fullmatch(idempotency_key)
        or not isinstance(request_fingerprint, str)
        or not _FINGERPRINT.fullmatch(request_fingerprint)
    ):
        raise AppError("IDEMPOTENCY_INVALID", "The request cannot be processed.", 400)

    # Injected checks must reload current permissions and resource visibility.
    authorize_operation(principal, operation_scope)
    if existing is None:
        return RequestDecision("execute")
    if (
        existing.principal_id != principal.user_id
        or existing.operation_scope != operation_scope
        or existing.idempotency_key != idempotency_key
    ):
        raise AppError("IDEMPOTENCY_UNAVAILABLE", "The request cannot be processed.", 404)
    if existing.status == "processing":
        raise AppError("IDEMPOTENCY_IN_PROGRESS", "The request is still in progress.", 409)
    if existing.status != "succeeded" or type(existing.response_status) is not int:
        raise AppError("IDEMPOTENCY_UNAVAILABLE", "The request cannot be processed.", 503)
    if (
        not 200 <= existing.response_status <= 299
        or not isinstance(existing.request_fingerprint, str)
        or not _FINGERPRINT.fullmatch(existing.request_fingerprint)
        or (existing.resource_type is None) != (existing.resource_id is None)
        or (existing.resource_type is not None and (
            not isinstance(existing.resource_type, str)
            or not existing.resource_type.strip()
            or not isinstance(existing.resource_id, UUID)
        ))
    ):
        raise AppError("IDEMPOTENCY_UNAVAILABLE", "The request cannot be processed.", 503)
    authorize_result(principal, existing.resource_type, existing.resource_id)
    if not hmac.compare_digest(existing.request_fingerprint, request_fingerprint):
        raise AppError("IDEMPOTENCY_CONFLICT", "This request key was already used.", 409)
    return RequestDecision(
        "replay", existing.response_status, existing.resource_type, existing.resource_id
    )
