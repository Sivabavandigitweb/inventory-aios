from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.models import AuditEvent
from app.services.audit import (
    AuditEventInput,
    AuditEventValidationError,
    build_audit_event,
    write_audit_event,
)


def make_event(**overrides: object) -> AuditEventInput:
    values: dict[str, object] = {
        "actor_user_id": uuid4(),
        "action": "employee.register",
        "entity_type": "employee",
        "entity_id": uuid4(),
        "change_source": "user",
        "metadata": {"changed_fields": ["department_id", "joining_date"]},
    }
    values.update(overrides)
    return AuditEventInput(**values)  # type: ignore[arg-type]


def test_audit_event_construction_attributes_local_actor_and_safe_metadata() -> None:
    event = make_event()
    row = build_audit_event(event)

    assert isinstance(row, AuditEvent)
    assert row.actor_user_id == event.actor_user_id
    assert row.action == "employee.register"
    assert row.entity_type == "employee"
    assert row.entity_id == event.entity_id
    assert row.change_source == "user"
    assert row.event_metadata == {"changed_fields": ["department_id", "joining_date"]}


def test_audit_writer_uses_callers_session_without_committing() -> None:
    session = MagicMock()
    event = make_event()

    result = write_audit_event(session, event)

    session.add.assert_called_once_with(result)
    session.flush.assert_called_once_with()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


def test_user_event_requires_actor() -> None:
    with pytest.raises(AuditEventValidationError):
        build_audit_event(make_event(actor_user_id=None))


def test_audit_event_rejects_secrets_and_confidential_values() -> None:
    with pytest.raises(AuditEventValidationError):
        build_audit_event(make_event(metadata={"access_token": "synthetic-secret"}))
    with pytest.raises(AuditEventValidationError):
        build_audit_event(make_event(metadata={"free_text": "synthetic confidential value"}))
    with pytest.raises(AuditEventValidationError):
        build_audit_event(make_event(metadata={"changed_fields": ["password"]}))


def test_audit_event_rejects_invalid_action_and_source() -> None:
    with pytest.raises(AuditEventValidationError):
        build_audit_event(make_event(action=" "))
    with pytest.raises(AuditEventValidationError):
        build_audit_event(make_event(change_source="unknown"))


def test_storage_failure_propagates_to_caller_for_rollback() -> None:
    session = MagicMock()
    session.flush.side_effect = RuntimeError("storage failed")

    with pytest.raises(RuntimeError, match="storage failed"):
        write_audit_event(session, make_event())

    session.commit.assert_not_called()


@pytest.mark.parametrize(
    "metadata",
    [
        {"extra": "not allowed"},
        {"request_id": {"nested": "value"}},
        {"request_id": "not-a-uuid"},
        {"changed_fields": "department_id"},
        {"changed_fields": ["department_id", 3]},
        {"changed_fields": ["department_id", "department_id"]},
        {"changed_fields": [f"field_{index}" for index in range(21)]},
        {"outcome": {"nested": "value"}},
        {"outcome": "pending"},
    ],
)
def test_audit_metadata_rejects_values_outside_database_contract(metadata: dict[str, object]) -> None:
    with pytest.raises(AuditEventValidationError):
        build_audit_event(make_event(metadata=metadata))
