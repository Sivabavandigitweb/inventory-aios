from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.authorization import Principal, authenticated_principal
from app.core.errors import AppError
from app.db.session import get_db_session
from app.main import app
from app.models import Department, Designation, Team, User
from app.schemas.employees import EmployeeCreate, EmployeeFilters
from app.services.audit import write_audit_event
from app.services.employees import get_employee, list_employees, register_employee


@pytest.fixture
def session() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(session: MagicMock):
    def override_session():
        yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[authenticated_principal] = lambda: Principal(
        user_id=uuid4(), permissions=frozenset({"employees:read:all", "employees:create"})
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def create_payload() -> EmployeeCreate:
    return EmployeeCreate(
        employee_number="TEST-001",
        first_name="Test",
        last_name="Employee",
        department_id=uuid4(),
        team_id=uuid4(),
        designation_id=uuid4(),
        joining_date=date(2026, 1, 5),
    )


def test_employee_request_validation_rejects_extra_and_blank_fields() -> None:
    with pytest.raises(ValueError):
        EmployeeCreate(
            employee_number=" ",
            first_name="Test",
            last_name="Employee",
            department_id=uuid4(),
            team_id=uuid4(),
            designation_id=uuid4(),
            joining_date=date(2026, 1, 5),
            email="private@example.invalid",
        )


def test_unauthenticated_registration_is_rejected_before_database_queries() -> None:
    session = MagicMock()
    app.dependency_overrides[get_db_session] = lambda: session
    with TestClient(app) as client:
        response = client.post("/api/v1/employees", json={})
    app.dependency_overrides.clear()
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    session.get.assert_not_called()
    session.scalars.assert_not_called()
def test_registration_endpoint_remains_disabled_without_audit_writer(client: TestClient) -> None:
    response = client.post("/api/v1/employees", json={"employee_number": "TEST-001"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUDIT_UNAVAILABLE"


def test_duplicate_identifier_is_rejected(session: MagicMock, create_payload: EmployeeCreate) -> None:
    actor_id = uuid4()
    session.get.side_effect = lambda model, key: {
        User: SimpleNamespace(id=actor_id),
        Department: SimpleNamespace(id=create_payload.department_id),
        Team: SimpleNamespace(id=create_payload.team_id, department_id=create_payload.department_id),
        Designation: SimpleNamespace(id=create_payload.designation_id),
    }.get(model)
    session.scalar.return_value = uuid4()

    with pytest.raises(AppError) as error:
        register_employee(session, create_payload, actor_id, MagicMock())

    assert error.value.code == "EMPLOYEE_EXISTS"
    session.rollback.assert_called_once()
    session.add.assert_not_called()


def test_invalid_organizational_reference_is_rejected(session: MagicMock, create_payload: EmployeeCreate) -> None:
    session.get.side_effect = lambda model, key: (
        SimpleNamespace(id=key) if model is User
        else SimpleNamespace(id=create_payload.department_id) if model is Department
        else None
    )
    with pytest.raises(AppError) as error:
        register_employee(session, create_payload, uuid4(), MagicMock())
    assert error.value.code == "INVALID_ORGANIZATION"
    assert error.value.status_code == 422
    session.rollback.assert_called_once()


def test_detail_not_found_returns_safe_not_found_error(session: MagicMock) -> None:
    session.get.return_value = None
    with pytest.raises(AppError) as error:
        get_employee(session, uuid4())
    assert error.value.code == "EMPLOYEE_NOT_FOUND"
    assert error.value.status_code == 404


def test_search_and_pagination_use_bounded_filters(session: MagicMock) -> None:
    employee = SimpleNamespace(
        id=uuid4(), employee_number="TEST-002", first_name="Test", last_name="Person",
        department_id=uuid4(), team_id=uuid4(), designation_id=uuid4(),
        joining_date=date(2026, 1, 5), status="active",
    )
    session.scalar.return_value = 1
    session.scalars.return_value = [employee]
    filters = EmployeeFilters(q="Test", limit=10, offset=0)

    page = list_employees(session, filters)

    assert page.total == 1
    assert page.items[0].employee_number == "TEST-002"
    assert page.limit == 10
    assert page.offset == 0
    assert session.scalar.call_args.args[0] is not None


def test_failed_registration_rolls_back_without_returning_details(
    session: MagicMock, create_payload: EmployeeCreate
) -> None:
    actor_id = uuid4()
    session.get.side_effect = lambda model, key: {
        User: SimpleNamespace(id=actor_id),
        Department: SimpleNamespace(id=create_payload.department_id),
        Team: SimpleNamespace(id=create_payload.team_id, department_id=create_payload.department_id),
        Designation: SimpleNamespace(id=create_payload.designation_id),
    }.get(model)
    session.scalar.return_value = None
    flush_calls = 0

    def fail_during_audit_flush():
        nonlocal flush_calls
        flush_calls += 1
        if flush_calls == 1:
            session.new[0].id = uuid4()
            return
        raise RuntimeError("synthetic audit storage failure")

    session.flush.side_effect = fail_during_audit_flush

    def fail_audit(session_arg, event):
        write_audit_event(session_arg, event)

    with pytest.raises(AppError) as error:
        register_employee(session, create_payload, actor_id, fail_audit)

    assert error.value.code == "REGISTRATION_FAILED"
    assert "synthetic" not in error.value.message
    session.rollback.assert_called_once()
    session.commit.assert_not_called()




def test_validation_error_does_not_echo_submitted_values(client: TestClient) -> None:
    response = client.get("/api/v1/employees/not-a-uuid")
    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert details
    assert all(set(item) == {"location", "type", "message"} for item in details)
    assert all("input" not in item for item in details)




def test_employee_read_permission_is_denied_without_explicit_grant(client: TestClient) -> None:
    from app.core.authorization import authenticated_principal

    app.dependency_overrides[authenticated_principal] = lambda: Principal(
        user_id=uuid4(), permissions=frozenset()
    )
    response = client.get("/api/v1/employees")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
