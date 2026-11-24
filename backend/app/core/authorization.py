from collections.abc import Callable
from typing import Annotated

from fastapi import Depends

from app.core.authentication import Principal, authenticated_principal
from app.core.errors import AppError


def require_permission(permission: str) -> Callable[..., Principal]:
    """Build a reusable fail-closed permission dependency."""

    def dependency(principal: Annotated[Principal, Depends(authenticated_principal)]) -> Principal:
        if permission not in principal.permissions:
            raise AppError("FORBIDDEN", "This operation is not permitted.", 403)
        return principal

    return dependency


require_employee_reader = require_permission("employees:read:all")
require_employee_registrar = require_permission("employees:create")
