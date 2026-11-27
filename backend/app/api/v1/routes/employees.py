from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.authorization import (
    Principal,
    require_employee_reader,
    require_employee_registrar,
    require_permission,
)
from app.core.errors import AppError
from app.db.session import get_db_session
from app.schemas.employees import (
    EmployeeCreate,
    EmployeeFilters,
    EmployeePage,
    EmployeeRead,
    EmployeeSyncStatus,
)
from app.services.employees import (
    AuditWriter,
    employee_audit_writer,
    employee_directory_summary,
    employee_sync_status,
    get_employee,
    list_employees,
    register_employee,
)

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("/sync-status", response_model=EmployeeSyncStatus)
def sync_status(
    principal: Annotated[Principal, Depends(require_permission("employee_sync:review"))],
    session: Annotated[Session, Depends(get_db_session)],
) -> EmployeeSyncStatus:
    del principal
    return employee_sync_status(session)


@router.post("/sync", status_code=503)
def run_sync(
    principal: Annotated[Principal, Depends(require_permission("employee_sync:run"))],
) -> None:
    del principal
    raise AppError("EMPLOYEE_SYNC_NOT_CONFIGURED",
                   "Authoritative source identity and field mapping are not configured.", 503)


@router.get("/summary")
def employee_summary(
    principal: Annotated[Principal, Depends(require_employee_reader)],
    session: Annotated[Session, Depends(get_db_session)],
) -> dict[str, int]:
    del principal
    return employee_directory_summary(session)


@router.post("", response_model=EmployeeRead, status_code=201)
def create_employee(
    payload: EmployeeCreate,
    principal: Annotated[Principal, Depends(require_employee_registrar)],
    audit: Annotated[AuditWriter, Depends(employee_audit_writer)],
    session: Annotated[Session, Depends(get_db_session)],
) -> EmployeeRead:
    return register_employee(session, payload, principal.user_id, audit)


@router.get("", response_model=EmployeePage)
def employee_directory(
    query: Annotated[EmployeeFilters, Query()],
    principal: Annotated[Principal, Depends(require_employee_reader)],
    session: Annotated[Session, Depends(get_db_session)],
) -> EmployeePage:
    return list_employees(session, query)


@router.get("/{employee_id}", response_model=EmployeeRead)
def employee_detail(
    employee_id: UUID,
    principal: Annotated[Principal, Depends(require_employee_reader)],
    session: Annotated[Session, Depends(get_db_session)],
) -> EmployeeRead:
    return get_employee(session, employee_id)
