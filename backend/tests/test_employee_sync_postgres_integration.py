"""Rollback-isolated PostgreSQL employee synchronization checks."""
from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_integration_test_settings
from app.core.integration_test_config import require_owner_test_url
from app.models import (
    AuditEvent,
    Department,
    Designation,
    Employee,
    EmployeeHistory,
    EmployeeSourceIdentity,
    EmployeeSyncRun,
    Team,
)
from app.services.audit import write_audit_event
from app.services.employee_sync import (
    OrganizationMapping,
    SourceEmployee,
    SqlAlchemyEmployeeSyncRepository,
    synchronize_employees,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def sync_session():
    settings = get_integration_test_settings()
    url = require_owner_test_url(settings.owner_database_url)
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
        assert connection.execute(text(
            "SELECT current_database(), session_user, current_user, inet_server_port(), "
            "(SELECT version_num FROM public.alembic_version)"
        )).one() == (
            "inventory_aios_restore_check", "inventory_aios_migrator", "inventory_aios_owner",
            5432, "d2a8f4c1b790",
        )
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
        engine.dispose()


def test_employee_sync_dry_run_insert_update_and_stable_identity(sync_session: Session) -> None:
    suffix = uuid4().hex
    department = Department(code=f"SYNC-{suffix}", name="TEST sync department")
    sync_session.add(department)
    sync_session.flush()
    team = Team(department_id=department.id, code=f"SYNC-{suffix}", name="TEST sync team")
    designation = Designation(code=f"SYNC-{suffix}", name="TEST sync designation")
    sync_session.add_all((team, designation))
    sync_session.flush()
    sync_session.commit()  # Commits only the session savepoint; the outer fixture rolls back.

    mapping = OrganizationMapping(
        departments={"DEPT-X": department.id},
        teams={"TEAM-X": team.id},
        designations={"ROLE-X": designation.id},
    )
    started = datetime.now(UTC)
    first = SourceEmployee(
        external_id=f"source-{suffix}", employee_number=f"TEST-{suffix}",
        first_name="Fictional", last_name="Person", department_code="DEPT-X",
        team_code="TEAM-X", designation_code="ROLE-X", joining_date=date(2025, 1, 2), status="active",
    )
    repository = SqlAlchemyEmployeeSyncRepository(sync_session, write_enabled=True, audit_complete=True)
    dry = synchronize_employees(
        source_key=f"test-{suffix}", source=type("Source", (), {"fetch_employees": lambda self: [first]})(),
        mapping=mapping, repository=repository, audit=write_audit_event, dry_run=True, now=started,
    )
    assert dry.counts.inserted == 1
    assert sync_session.scalar(select(EmployeeSourceIdentity).where(
        EmployeeSourceIdentity.source_key == f"test-{suffix}"
    )) is None
    sync_session.commit()

    inserted = synchronize_employees(
        source_key=f"test-{suffix}", source=type("Source", (), {"fetch_employees": lambda self: [first]})(),
        mapping=mapping, repository=repository, audit=write_audit_event, dry_run=False, now=started,
    )
    assert inserted.status == "succeeded" and inserted.counts.inserted == 1
    identity = sync_session.get(EmployeeSourceIdentity, (f"test-{suffix}", first.external_id))
    assert identity is not None
    employee_id = identity.employee_id
    sync_session.commit()

    unchanged = synchronize_employees(
        source_key=f"test-{suffix}", source=type("Source", (), {"fetch_employees": lambda self: [first]})(),
        mapping=mapping, repository=repository, audit=write_audit_event, dry_run=False, now=started,
    )
    assert unchanged.counts.unchanged == 1

    updated_source = SourceEmployee(
        external_id=first.external_id, employee_number=first.employee_number,
        first_name=first.first_name, last_name="Updated", department_code=first.department_code,
        team_code=first.team_code, designation_code=first.designation_code,
        joining_date=first.joining_date, status="inactive",
    )
    updated = synchronize_employees(
        source_key=f"test-{suffix}",
        source=type("Source", (), {"fetch_employees": lambda self: [updated_source]})(),
        mapping=mapping, repository=repository, audit=write_audit_event, dry_run=False,
        now=datetime.now(UTC),
    )
    employee = sync_session.get(Employee, employee_id)
    assert updated.counts.updated == 1
    assert employee is not None and employee.last_name == "Updated" and employee.status == "inactive"
    assert sync_session.scalar(select(EmployeeSourceIdentity.employee_id).where(
        EmployeeSourceIdentity.source_key == f"test-{suffix}",
        EmployeeSourceIdentity.external_id == first.external_id,
    )) == employee_id
    assert sync_session.scalar(select(func.count()).select_from(EmployeeHistory).where(
        EmployeeHistory.employee_id == employee_id
    )) == 2
    assert sync_session.scalar(select(EmployeeSyncRun.id).where(
        EmployeeSyncRun.source_key == f"test-{suffix}", EmployeeSyncRun.status == "succeeded"
    ).limit(1)) is not None
    assert sync_session.scalar(select(AuditEvent.id).where(
        AuditEvent.entity_type == "employee", AuditEvent.entity_id == employee_id
    ).limit(1)) is not None
