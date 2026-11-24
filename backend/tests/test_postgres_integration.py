from __future__ import annotations

import time
import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import get_integration_test_settings
from app.core.integration_test_config import require_isolated_test_url, require_owner_test_url
from app.models import Department, Employee, EmployeeHistory, User

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def runtime_postgres_engine():
    settings = get_integration_test_settings()
    try:
        database_url = require_isolated_test_url(settings.database_url)
    except RuntimeError as exc:
        if settings.database_url is None:
            pytest.skip("INVENTORY_TEST_DATABASE_URL is not configured in .test.env.")
        pytest.fail(str(exc))
    engine = create_engine(database_url, pool_pre_ping=True, hide_parameters=True)
    with engine.connect() as connection:
        database, session_user, current_user, port = connection.execute(
            text("SELECT current_database(), session_user, current_user, inet_server_port()")
        ).one()
        if (database, session_user, current_user, port) != (
            "inventory_aios_restore_check", "inventory_aios_app", "inventory_aios_app", 5432
        ):
            engine.dispose()
            pytest.fail("PostgreSQL integration test connection identity was rejected.")
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def owner_postgres_engine():
    settings = get_integration_test_settings()
    try:
        database_url = require_owner_test_url(settings.owner_database_url)
    except RuntimeError as exc:
        if settings.owner_database_url is None:
            pytest.skip("Owner test URL is not configured in .test.env.")
        pytest.fail(str(exc))
    engine = create_engine(database_url, pool_pre_ping=True, hide_parameters=True)
    yield engine
    engine.dispose()


@pytest.fixture
def owner_db_session(owner_postgres_engine) -> Generator[Session, None, None]:
    with owner_postgres_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            connection.execute(text("SET ROLE inventory_aios_owner"))
            session_user, current_user = connection.execute(
                text("SELECT session_user, current_user")
            ).one()
            assert (session_user, current_user) == (
                "inventory_aios_migrator", "inventory_aios_owner"
            )
            yield session
        finally:
            session.close()
            transaction.rollback()


def test_postgresql_generates_uuid_primary_key(owner_db_session: Session) -> None:
    code = f"TEST_UUID_{uuid.uuid4().hex}"
    row = owner_db_session.execute(
        text(
            "INSERT INTO departments (code, name, active) "
            "VALUES (:code, :name, true) RETURNING id"
        ),
        {"code": code, "name": "TEST UUID Department"},
    ).one()

    assert isinstance(row.id, uuid.UUID)


def test_updated_at_changes_after_postgresql_update(owner_db_session: Session) -> None:
    department = Department(
        code=f"TEST_TIMESTAMP_{uuid.uuid4().hex}",
        name="TEST Timestamp Department",
    )
    owner_db_session.add(department)
    owner_db_session.flush()
    original_updated_at = department.updated_at

    time.sleep(0.01)
    department.name = "TEST Timestamp Department Updated"
    owner_db_session.flush()
    owner_db_session.refresh(department)

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


def test_employee_history_rejects_update(owner_db_session: Session) -> None:
    employee, user = _create_history_context(owner_db_session)
    history = _create_history(owner_db_session, employee, user)

    with pytest.raises(DBAPIError):
        with owner_db_session.begin_nested():
            owner_db_session.execute(
                text("UPDATE employee_history SET reason=:reason WHERE id=:id"),
                {"reason": "TEST unauthorized rewrite", "id": history.id},
            )

    reason = owner_db_session.execute(
        text("SELECT reason FROM employee_history WHERE id=:id"), {"id": history.id}
    ).scalar_one()
    assert reason == "TEST history event"


def test_employee_history_rejects_delete(owner_db_session: Session) -> None:
    employee, user = _create_history_context(owner_db_session)
    history = _create_history(owner_db_session, employee, user)

    with pytest.raises(DBAPIError):
        with owner_db_session.begin_nested():
            owner_db_session.execute(
                text("DELETE FROM employee_history WHERE id=:id"), {"id": history.id}
            )

    assert owner_db_session.execute(
        text("SELECT count(*) FROM employee_history WHERE id=:id"), {"id": history.id}
    ).scalar_one() == 1


def test_employee_history_source_and_actor_validation(owner_db_session: Session) -> None:
    employee, user = _create_history_context(owner_db_session)

    with pytest.raises(DBAPIError):
        with owner_db_session.begin_nested():
            owner_db_session.execute(
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
        owner_db_session.add(history)
        owner_db_session.flush()
        assert history.id is not None

    assert user.id is not None


def test_foreign_key_constraint_is_enforced(owner_db_session: Session) -> None:
    with pytest.raises(DBAPIError):
        with owner_db_session.begin_nested():
            owner_db_session.execute(
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


def test_unique_constraint_is_enforced(owner_db_session: Session) -> None:
    code = f"TEST_UNIQUE_{uuid.uuid4().hex}"
    owner_db_session.add(Department(code=code, name="TEST Unique Department"))
    owner_db_session.flush()

    with pytest.raises(DBAPIError):
        with owner_db_session.begin_nested():
            owner_db_session.add(Department(code=code, name="TEST Duplicate Department"))
            owner_db_session.flush()


def test_outer_transaction_rolls_back_synthetic_records(owner_db_session: Session) -> None:
    department = Department(
        code=f"TEST_ROLLBACK_{uuid.uuid4().hex}",
        name="TEST Rollback Department",
    )
    owner_db_session.add(department)
    owner_db_session.flush()

    assert owner_db_session.execute(
        text("SELECT count(*) FROM departments WHERE code=:code"),
        {"code": department.code},
    ).scalar_one() == 1

def test_runtime_role_lacks_history_mutation_and_schema_privileges(runtime_postgres_engine) -> None:
    with runtime_postgres_engine.connect() as connection:
        privileges = connection.execute(
            text(
                "SELECT current_user, "
                "has_table_privilege(current_user, 'public.employee_history', 'UPDATE'), "
                "has_table_privilege(current_user, 'public.employee_history', 'DELETE'), "
                "has_table_privilege(current_user, 'public.employee_history', 'TRUNCATE'), "
                "has_schema_privilege(current_user, 'public', 'CREATE')"
            )
        ).one()
    assert privileges == ("inventory_aios_app", False, False, False, False)
