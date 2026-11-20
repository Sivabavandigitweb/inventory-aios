from __future__ import annotations

import time
import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_engine
from app.models import Department, Employee, EmployeeHistory, User

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_engine():
    settings = get_settings()
    assert settings.database_url is not None
    assert "localhost" in settings.database_url
    engine = get_engine()
    with engine.connect() as connection:
        identity = connection.execute(
            text("SELECT current_database(), inet_server_port()")
        ).one()
        assert identity[0] == "inventory_aios_dev"
        assert identity[1] == 5432
    return engine


@pytest.fixture
def db_session(postgres_engine) -> Generator[Session, None, None]:
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


def test_postgresql_generates_uuid_primary_key(db_session: Session) -> None:
    code = f"TEST_UUID_{uuid.uuid4().hex}"
    row = db_session.execute(
        text(
            "INSERT INTO departments (code, name, active) "
            "VALUES (:code, :name, true) RETURNING id"
        ),
        {"code": code, "name": "TEST UUID Department"},
    ).one()

    assert isinstance(row.id, uuid.UUID)


def test_updated_at_changes_after_postgresql_update(db_session: Session) -> None:
    department = Department(
        code=f"TEST_TIMESTAMP_{uuid.uuid4().hex}",
        name="TEST Timestamp Department",
    )
    db_session.add(department)
    db_session.flush()
    original_updated_at = department.updated_at

    time.sleep(0.01)
    department.name = "TEST Timestamp Department Updated"
    db_session.flush()
    db_session.refresh(department)

    assert department.updated_at > original_updated_at


def _create_history_context(session: Session) -> tuple[Employee, User]:
    employee = Employee(
        employee_number=f"TEST_EMP_{uuid.uuid4().hex}",
        first_name="TEST",
        last_name="Employee",
        status="active",
    )
    session.add(employee)
    session.flush()

    user = User(
        username=f"TEST_USER_{uuid.uuid4().hex}",
        email=f"test_{uuid.uuid4().hex}@example.invalid",
        display_name="TEST User",
        employee_id=employee.id,
    )
    session.add(user)
    session.flush()
    return employee, user


def _create_history(session: Session, employee: Employee, user: User) -> EmployeeHistory:
    history = EmployeeHistory(
        employee_id=employee.id,
        change_type="transfer",
        changed_by_id=user.id,
        change_source="user",
        reason="TEST history event",
    )
    session.add(history)
    session.flush()
    return history


def test_employee_history_rejects_update(db_session: Session) -> None:
    employee, user = _create_history_context(db_session)
    history = _create_history(db_session, employee, user)

    with pytest.raises(DBAPIError):
        with db_session.begin_nested():
            db_session.execute(
                text("UPDATE employee_history SET reason=:reason WHERE id=:id"),
                {"reason": "TEST unauthorized rewrite", "id": history.id},
            )

    reason = db_session.execute(
        text("SELECT reason FROM employee_history WHERE id=:id"), {"id": history.id}
    ).scalar_one()
    assert reason == "TEST history event"


def test_employee_history_rejects_delete(db_session: Session) -> None:
    employee, user = _create_history_context(db_session)
    history = _create_history(db_session, employee, user)

    with pytest.raises(DBAPIError):
        with db_session.begin_nested():
            db_session.execute(
                text("DELETE FROM employee_history WHERE id=:id"), {"id": history.id}
            )

    assert db_session.execute(
        text("SELECT count(*) FROM employee_history WHERE id=:id"), {"id": history.id}
    ).scalar_one() == 1


def test_employee_history_source_and_actor_validation(db_session: Session) -> None:
    employee, user = _create_history_context(db_session)

    with pytest.raises(DBAPIError):
        with db_session.begin_nested():
            db_session.execute(
                text(
                    "INSERT INTO employee_history "
                    "(employee_id, change_type, changed_by_id, change_source, reason) "
                    "VALUES (:employee_id, 'transfer', NULL, 'user', 'TEST invalid actor')"
                ),
                {"employee_id": employee.id},
            )

    for source in ("system", "import"):
        history = EmployeeHistory(
            employee_id=employee.id,
            change_type="onboarding",
            changed_by_id=None,
            change_source=source,
            reason=f"TEST {source} event",
        )
        db_session.add(history)
        db_session.flush()
        assert history.id is not None

    assert user.id is not None


def test_foreign_key_constraint_is_enforced(db_session: Session) -> None:
    with pytest.raises(DBAPIError):
        with db_session.begin_nested():
            db_session.execute(
                text(
                    "INSERT INTO teams (department_id, code, name, active) "
                    "VALUES (:department_id, :code, :name, true)"
                ),
                {
                    "department_id": uuid.uuid4(),
                    "code": f"TEST_TEAM_{uuid.uuid4().hex}",
                    "name": "TEST Team",
                },
            )


def test_unique_constraint_is_enforced(db_session: Session) -> None:
    code = f"TEST_UNIQUE_{uuid.uuid4().hex}"
    db_session.add(Department(code=code, name="TEST Unique Department"))
    db_session.flush()

    with pytest.raises(DBAPIError):
        with db_session.begin_nested():
            db_session.add(Department(code=code, name="TEST Duplicate Department"))
            db_session.flush()


def test_outer_transaction_rolls_back_synthetic_records(db_session: Session) -> None:
    department = Department(
        code=f"TEST_ROLLBACK_{uuid.uuid4().hex}",
        name="TEST Rollback Department",
    )
    db_session.add(department)
    db_session.flush()

    assert db_session.execute(
        text("SELECT count(*) FROM departments WHERE code=:code"),
        {"code": department.code},
    ).scalar_one() == 1