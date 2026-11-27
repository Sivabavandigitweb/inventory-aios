from collections.abc import Callable
from typing import Annotated, Protocol
from uuid import UUID

from fastapi import Depends

from app.core.authentication import Principal, authenticated_principal
from app.core.errors import AppError
from app.core.permission_catalog import is_known_capability


def require_permission(permission: str) -> Callable[..., Principal]:
    """Build a reusable fail-closed permission dependency."""

    if not is_known_capability(permission):
        raise ValueError("Unknown capability identifier.")

    def dependency(principal: Annotated[Principal, Depends(authenticated_principal)]) -> Principal:
        if permission not in principal.permissions:
            raise AppError("FORBIDDEN", "This operation is not permitted.", 403)
        return principal

    return dependency


require_employee_reader = require_permission("employees:read:all")
require_employee_registrar = require_permission("employees:create")


class ResourceAuthorizer(Protocol):
    """Injected server-side resource-scope policy; never a client-supplied scope."""

    def can_access(
        self, *, user_id: UUID, capability: str, resource_type: str, resource_id: UUID
    ) -> bool: ...


def authorize_resource(
    principal: Principal,
    *,
    capability: str,
    resource_type: str,
    resource_id: UUID,
    authorizer: ResourceAuthorizer,
) -> None:
    """Enforce both the known capability and an injected object-scope decision."""

    if not is_known_capability(capability):
        raise AppError("AUTHORIZATION_UNAVAILABLE", "Authorization is temporarily unavailable.", 503)
    if capability not in principal.permissions:
        raise AppError("FORBIDDEN", "This operation is not permitted.", 403)
    if not isinstance(resource_type, str) or not resource_type or not isinstance(resource_id, UUID):
        raise AppError("AUTHORIZATION_UNAVAILABLE", "Authorization is temporarily unavailable.", 503)
    try:
        decision = authorizer.can_access(
            user_id=principal.user_id,
            capability=capability,
            resource_type=resource_type,
            resource_id=resource_id,
        )
    except Exception:
        raise AppError("AUTHORIZATION_UNAVAILABLE", "Authorization is temporarily unavailable.", 503) from None
    if decision is not True:
        raise AppError("FORBIDDEN", "This operation is not permitted.", 403)
