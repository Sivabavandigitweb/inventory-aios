from fastapi import Depends

from app.core.authentication import Principal, authenticated_principal
from app.core.errors import AppError


def require_employee_reader(principal: Principal = Depends(authenticated_principal)) -> Principal:
    if "employees:read:all" not in principal.permissions:
        raise AppError("FORBIDDEN", "Employee directory access is not permitted.", 403)
    return principal


def require_employee_registrar(principal: Principal = Depends(authenticated_principal)) -> Principal:
    if "employees:create" not in principal.permissions:
        raise AppError("FORBIDDEN", "Employee registration is not permitted.", 403)
    return principal
