from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import Department, Designation, Employee, EmployeeHistory, Team, User
from app.schemas.employees import EmployeeCreate, EmployeeFilters, EmployeePage, EmployeeRead

AuditWriter = Callable[[Session, dict[str, object]], None]


def employee_audit_writer() -> AuditWriter:
    raise AppError("AUDIT_UNAVAILABLE", "Employee registration is not enabled yet.", 503)


def register_employee(session: Session, payload: EmployeeCreate, actor_id: UUID, audit: AuditWriter) -> EmployeeRead:
    try:
        if session.get(User, actor_id) is None:
            raise AppError("FORBIDDEN", "An attributable application user is required.", 403)
        department = session.get(Department, payload.department_id)
        team = session.get(Team, payload.team_id)
        designation = session.get(Designation, payload.designation_id)
        if department is None or team is None or designation is None:
            raise AppError("INVALID_ORGANIZATION", "Organizational reference does not exist.", 422)
        if team.department_id != department.id:
            raise AppError("INVALID_ORGANIZATION", "Team does not belong to department.", 422)
        if session.scalar(select(Employee.id).where(Employee.employee_number == payload.employee_number)):
            raise AppError("EMPLOYEE_EXISTS", "Employee identifier already exists.", 409)
        employee = Employee(**payload.model_dump())
        session.add(employee)
        session.flush()
        result = EmployeeRead.model_validate(employee)
        session.add(EmployeeHistory(
            employee_id=employee.id, new_department_id=employee.department_id,
            new_team_id=employee.team_id, new_designation_id=employee.designation_id,
            change_type="onboarding", changed_by_id=actor_id, change_source="user",
            reason="Employee registration",
        ))
        audit(session, {
            "actor_user_id": str(actor_id), "occurred_at": datetime.now(timezone.utc).isoformat(),
            "entity_type": "employee", "entity_id": str(employee.id), "action": "register",
            "previous_value": None, "new_value": result.model_dump(mode="json"),
        })
        session.flush()
        session.commit()
        return result
    except IntegrityError as exc:
        session.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_employees_employee_number":
            raise AppError("EMPLOYEE_EXISTS", "Employee identifier already exists.", 409) from None
        raise AppError("EMPLOYEE_CONFLICT", "Employee data conflicts with database constraints.", 409) from None
    except AppError:
        session.rollback()
        raise
    except Exception:
        session.rollback()
        raise AppError("REGISTRATION_FAILED", "Employee registration could not be completed.", 503) from None


def get_employee(session: Session, employee_id: UUID) -> EmployeeRead:
    try:
        employee = session.get(Employee, employee_id)
        if employee is None:
            raise AppError("EMPLOYEE_NOT_FOUND", "Employee not found.", 404)
        return EmployeeRead.model_validate(employee)
    except SQLAlchemyError:
        session.rollback()
        raise AppError("DATABASE_UNAVAILABLE", "Employee lookup is unavailable.", 503) from None


def list_employees(session: Session, filters: EmployeeFilters) -> EmployeePage:
    clauses = []
    for field in ("department_id", "team_id", "designation_id", "status"):
        value = getattr(filters, field)
        if value is not None:
            clauses.append(getattr(Employee, field) == value)
    if filters.q:
        escaped = filters.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        clauses.append(or_(Employee.employee_number.ilike(pattern, escape="\\"),
            Employee.first_name.ilike(pattern, escape="\\"), Employee.last_name.ilike(pattern, escape="\\"),
            (Employee.first_name + " " + Employee.last_name).ilike(pattern, escape="\\")))
    try:
        total = session.scalar(select(func.count()).select_from(Employee).where(*clauses)) or 0
        rows = session.scalars(select(Employee).where(*clauses).order_by(
            Employee.employee_number, Employee.id).limit(filters.limit).offset(filters.offset))
        return EmployeePage(items=[EmployeeRead.model_validate(row) for row in rows],
            total=total, limit=filters.limit, offset=filters.offset)
    except SQLAlchemyError:
        session.rollback()
        raise AppError("DATABASE_UNAVAILABLE", "Employee search is unavailable.", 503) from None