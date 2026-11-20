from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.authorization import Principal, require_employee_reader, require_employee_registrar
from app.db.session import get_db_session
from app.schemas.employees import EmployeeCreate, EmployeeFilters, EmployeePage, EmployeeRead
from app.services.employees import (
    AuditWriter,
    employee_audit_writer,
    get_employee,
    list_employees,
    register_employee,
)

router = APIRouter(prefix="/employees", tags=["employees"])


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