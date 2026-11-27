"""Provider-independent employee synchronization; source access is never implicit."""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    Department,
    Designation,
    Employee,
    EmployeeHistory,
    EmployeeSourceIdentity,
    EmployeeSyncRun,
    Team,
)
from app.services.audit import AuditEventInput

AuditWriter = Callable[[Session, AuditEventInput], object]

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,199}$")
_SOURCE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$")


@dataclass(frozen=True)
class SourceEmployee:
    external_id: str
    employee_number: str
    first_name: str
    last_name: str
    department_code: str
    team_code: str
    designation_code: str
    joining_date: date | None
    status: str


class EmployeeSource(Protocol):
    def fetch_employees(self) -> Sequence[SourceEmployee]: ...


@dataclass(frozen=True)
class OrganizationMapping:
    departments: Mapping[str, UUID]
    teams: Mapping[str, UUID]
    designations: Mapping[str, UUID]


@dataclass(frozen=True)
class SyncCounts:
    read: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    conflicts: int = 0


@dataclass(frozen=True)
class SyncResult:
    run_id: UUID
    source_key: str
    status: str
    dry_run: bool
    counts: SyncCounts
    completed_at: datetime


class EmployeeSyncRepository(Protocol):
    def synchronize(self, *, source_key: str, rows: Sequence[SourceEmployee], mapping: OrganizationMapping,
                    dry_run: bool, audit: AuditWriter, started_at: datetime) -> SyncResult: ...


def _validate_rows(rows: Sequence[SourceEmployee]) -> None:
    if any(not isinstance(row, SourceEmployee) for row in rows):
        raise AppError("EMPLOYEE_SYNC_INVALID", "Source employee data is invalid.", 422)
    if any(not isinstance(row.external_id, str) or not isinstance(row.employee_number, str)
           for row in rows):
        raise AppError("EMPLOYEE_SYNC_INVALID", "Source employee data is invalid.", 422)
    external_ids = Counter(row.external_id for row in rows)
    employee_numbers = Counter(row.employee_number for row in rows)
    if any(value != 1 for value in external_ids.values()) or any(value != 1 for value in employee_numbers.values()):
        raise AppError("EMPLOYEE_SYNC_CONFLICT", "Source contains conflicting employee identities.", 409)
    for row in rows:
        if (not isinstance(row.external_id, str) or not isinstance(row.employee_number, str)
                or not _IDENTIFIER.fullmatch(row.external_id) or not row.employee_number.strip()
                or len(row.employee_number) > 50):
            raise AppError("EMPLOYEE_SYNC_INVALID", "Source employee data is invalid.", 422)
        if (any(not isinstance(value, str) or not value.strip() for value in
                (row.first_name, row.last_name, row.department_code, row.team_code, row.designation_code))
                or len(row.first_name) > 100 or len(row.last_name) > 100):
            raise AppError("EMPLOYEE_SYNC_INVALID", "Source employee data is invalid.", 422)
        if row.status not in {"active", "inactive"}:
            raise AppError("EMPLOYEE_SYNC_INVALID", "Source employee status is unsupported.", 422)


def synchronize_employees(*, source_key: str, source: EmployeeSource, mapping: OrganizationMapping,
                          repository: EmployeeSyncRepository, audit: AuditWriter,
                          dry_run: bool = True, now: datetime | None = None) -> SyncResult:
    """Fetch and validate one complete source snapshot, then apply atomically."""
    if not isinstance(source_key, str) or not _SOURCE_KEY.fullmatch(source_key):
        raise AppError("EMPLOYEE_SYNC_CONFIG_INVALID", "Employee source is not configured.", 503)
    try:
        rows = tuple(source.fetch_employees())
    except Exception:
        raise AppError("EMPLOYEE_SOURCE_UNAVAILABLE", "Employee source is unavailable.", 503) from None
    _validate_rows(rows)
    started = now or datetime.now(timezone.utc)
    if started.tzinfo is None or started.utcoffset() is None:
        raise AppError("EMPLOYEE_SYNC_INVALID", "Synchronization time must be timezone-aware.", 422)
    return repository.synchronize(source_key=source_key, rows=rows, mapping=mapping,
                                  dry_run=dry_run, audit=audit, started_at=started)


class SqlAlchemyEmployeeSyncRepository:
    """Local DB adapter. Source retrieval remains a distinct injected read-only provider."""

    def __init__(self, session: Session, *, write_enabled: bool = False, audit_complete: bool = False):
        self.session = session
        self.write_enabled = write_enabled
        self.audit_complete = audit_complete

    def synchronize(self, *, source_key: str, rows: Sequence[SourceEmployee], mapping: OrganizationMapping,
                    dry_run: bool, audit: AuditWriter, started_at: datetime) -> SyncResult:
        if not dry_run and not (self.write_enabled and self.audit_complete):
            raise AppError("EMPLOYEE_SYNC_NOT_ENABLED",
                           "Employee synchronization writes require approved source mapping and complete audit controls.", 503)
        run_id = uuid4()
        counts = {"inserted": 0, "updated": 0, "unchanged": 0, "conflicts": 0}
        try:
            with self.session.begin():
                run = EmployeeSyncRun(id=run_id, source_key=source_key, started_at=started_at,
                    status="running", dry_run=dry_run, read_count=len(rows))
                self.session.add(run)
                for row in rows:
                    department_id = mapping.departments.get(row.department_code)
                    team_id = mapping.teams.get(row.team_code)
                    designation_id = mapping.designations.get(row.designation_code)
                    department = self.session.get(Department, department_id) if department_id else None
                    team = self.session.get(Team, team_id) if team_id else None
                    designation = self.session.get(Designation, designation_id) if designation_id else None
                    if not department or not team or not designation or team.department_id != department.id:
                        raise AppError("EMPLOYEE_SYNC_MAPPING_INVALID", "Organization mapping is invalid.", 422)

                    identity = self.session.get(EmployeeSourceIdentity, (source_key, row.external_id))
                    number_owner = self.session.scalar(select(Employee).where(
                        Employee.employee_number == row.employee_number))
                    if identity and number_owner and number_owner.id != identity.employee_id:
                        raise AppError("EMPLOYEE_SYNC_CONFLICT", "Employee source identity conflicts with a local record.", 409)
                    if identity:
                        employee = self.session.get(Employee, identity.employee_id)
                        if employee is None:
                            raise AppError("EMPLOYEE_SYNC_CONFLICT", "Employee source identity is inconsistent.", 409)
                    elif number_owner:
                        raise AppError("EMPLOYEE_SYNC_CONFLICT", "Employee number is already linked to another identity.", 409)
                    else:
                        employee = None

                    values = dict(employee_number=row.employee_number, first_name=row.first_name.strip(),
                        last_name=row.last_name.strip(), department_id=department.id, team_id=team.id,
                        designation_id=designation.id, joining_date=row.joining_date, status=row.status)
                    if employee is None:
                        counts["inserted"] += 1
                        if dry_run:
                            continue
                        employee = Employee(**values)
                        self.session.add(employee)
                        self.session.flush()
                        self.session.add(EmployeeSourceIdentity(source_key=source_key,
                            external_id=row.external_id, employee_id=employee.id, last_seen_at=started_at))
                        self.session.add(EmployeeHistory(employee_id=employee.id,
                            new_department_id=department.id, new_team_id=team.id,
                            new_designation_id=designation.id, change_type="source_sync",
                            changed_by_id=None, change_source="import", reason="Authoritative employee synchronization"))
                        audit(self.session, AuditEventInput(actor_user_id=None, action="synchronize",
                            entity_type="employee", entity_id=employee.id, change_source="import",
                            metadata={"changed_fields": sorted(values.keys())}))
                        continue

                    changed = {name: value for name, value in values.items() if getattr(employee, name) != value}
                    if not changed:
                        counts["unchanged"] += 1
                    else:
                        counts["updated"] += 1
                        if not dry_run:
                            old = {name: getattr(employee, name) for name in changed}
                            for name, value in changed.items():
                                setattr(employee, name, value)
                            self.session.add(EmployeeHistory(employee_id=employee.id,
                                old_department_id=old.get("department_id"), new_department_id=department.id,
                                old_team_id=old.get("team_id"), new_team_id=team.id,
                                old_designation_id=old.get("designation_id"), new_designation_id=designation.id,
                                change_type="source_sync", changed_by_id=None, change_source="import",
                                reason="Authoritative employee synchronization"))
                            audit(self.session, AuditEventInput(actor_user_id=None, action="synchronize",
                                entity_type="employee", entity_id=employee.id, change_source="import",
                                metadata={"changed_fields": sorted(changed.keys())}))
                        if identity and not dry_run:
                            identity.last_seen_at = started_at
                completed = datetime.now(timezone.utc)
                if dry_run:
                    run.status = "dry_run"
                else:
                    run.status = "succeeded"
                run.finished_at = completed
                run.inserted_count = counts["inserted"]
                run.updated_count = counts["updated"]
                run.unchanged_count = counts["unchanged"]
                run.conflict_count = counts["conflicts"]
            return SyncResult(run_id, source_key, "dry_run" if dry_run else "succeeded", dry_run,
                SyncCounts(read=len(rows), **counts), completed)
        except AppError:
            self.session.rollback()
            raise
        except IntegrityError:
            self.session.rollback()
            raise AppError("EMPLOYEE_SYNC_CONFLICT", "Employee synchronization conflicts with current records.", 409) from None
        except SQLAlchemyError:
            self.session.rollback()
            raise AppError("EMPLOYEE_SYNC_UNAVAILABLE", "Employee synchronization is unavailable.", 503) from None


class ConfiguredReadOnlyPostgresSource:
    """Configured source adapter; validates identifiers and opens no connection on construction."""

    def __init__(self, session_factory, *, table: str, column_map: Mapping[str, str]):
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?", table):
            raise ValueError("Invalid source table configuration")
        if set(column_map) != {"external_id", "employee_number", "first_name", "last_name", "department_code", "team_code", "designation_code", "joining_date", "status"}:
            raise ValueError("Source field mapping is incomplete")
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) for value in column_map.values()):
            raise ValueError("Invalid source column configuration")
        self.session_factory, self.table, self.column_map = session_factory, table, dict(column_map)

    def fetch_employees(self) -> Sequence[SourceEmployee]:
        from sqlalchemy import text
        columns = ", ".join(f'"{name}" AS "{alias}"' for alias, name in self.column_map.items())
        try:
            with self.session_factory() as session:
                with session.begin():
                    session.execute(text("SET TRANSACTION READ ONLY"))
                    rows = session.execute(text(f"SELECT {columns} FROM {self.table}"))
                    return tuple(SourceEmployee(**dict(row._mapping)) for row in rows)
        except SQLAlchemyError:
            raise AppError("EMPLOYEE_SOURCE_UNAVAILABLE", "Employee source is unavailable.", 503) from None
