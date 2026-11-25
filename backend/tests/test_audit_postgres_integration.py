from __future__ import annotations

import json
import re
import uuid
from collections.abc import Generator
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import get_integration_test_settings
from app.core.integration_test_config import require_isolated_test_url, require_owner_test_url
from app.models import AuditEvent, User
from app.services.audit import AuditEventInput, write_audit_event

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def owner_engine() -> Generator[Engine, None, None]:
    settings = get_integration_test_settings()
    engine = create_engine(
        require_owner_test_url(settings.owner_database_url),
        pool_pre_ping=True,
        hide_parameters=True,
    )
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def runtime_engine() -> Generator[Engine, None, None]:
    settings = get_integration_test_settings()
    engine = create_engine(
        require_isolated_test_url(settings.database_url),
        pool_pre_ping=True,
        hide_parameters=True,
    )
    yield engine
    engine.dispose()


@pytest.fixture
def owner_session(owner_engine: Engine) -> Generator[Session, None, None]:
    with owner_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            assert connection.execute(
                text("SELECT current_database(), session_user, current_user, inet_server_port()")
            ).one() == (
                "inventory_aios_restore_check",
                "inventory_aios_migrator",
                "inventory_aios_migrator",
                5432,
            )
            connection.execute(text("SET ROLE inventory_aios_owner"))
            assert connection.execute(text("SELECT session_user, current_user")).one() == (
                "inventory_aios_migrator",
                "inventory_aios_owner",
            )
            yield session
        finally:
            session.close()
            transaction.rollback()


def _sqlstate(error: DBAPIError) -> str | None:
    return getattr(error.orig, "sqlstate", None) or getattr(error.orig, "pgcode", None)


def _constraint(error: DBAPIError) -> str | None:
    return getattr(getattr(error.orig, "diag", None), "constraint_name", None)


def _expect_error(
    session: Session,
    sql: str,
    parameters: dict[str, object],
    state: str,
    constraint: str | None = None,
) -> None:
    with pytest.raises(DBAPIError) as error:
        with session.begin_nested():
            session.execute(text(sql), parameters)
    assert _sqlstate(error.value) == state
    if state == "23502":
        assert getattr(getattr(error.value.orig, "diag", None), "column_name", None) == "action"
    if constraint:
        assert _constraint(error.value) == constraint


def _values(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "actor_user_id": None,
        "action": "audit.test",
        "entity_type": "test_entity",
        "entity_id": uuid.uuid4(),
        "change_source": "system",
        "metadata": "{}",
    }
    data.update(overrides)
    return data


INSERT_AUDIT = (
    "INSERT INTO public.audit_events "
    "(actor_user_id, action, entity_type, entity_id, change_source, metadata) "
    "VALUES (:actor_user_id, :action, :entity_type, :entity_id, :change_source, "
    "CAST(:metadata AS jsonb))"
)


def _actor(session: Session) -> User:
    actor = User(
        username=f"TEST_AUDIT_{uuid.uuid4().hex}",
        email=f"test_audit_{uuid.uuid4().hex}@example.invalid",
        display_name="TEST Audit Actor",
        status="active",
    )
    session.add(actor)
    session.flush()
    return actor


def _read_owner_count(engine: Engine, sql: str, parameters: dict[str, object]) -> int:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET ROLE inventory_aios_owner"))
            return int(connection.execute(text(sql), parameters).scalar_one())
        finally:
            transaction.rollback()


def test_writer_flushes_in_callers_transaction_and_returns_server_timestamp(
    owner_engine: Engine, owner_session: Session
) -> None:
    actor = _actor(owner_session)
    statements: list[str] = []
    commits: list[bool] = []

    def capture(connection, cursor, statement, parameters, context, executemany) -> None:
        if statement.lstrip().lower().startswith("insert into public.audit_events"):
            statements.append(statement)

    def committed(session: Session) -> None:
        commits.append(True)

    connection = owner_session.connection()
    event.listen(connection, "before_cursor_execute", capture)
    event.listen(owner_session, "after_commit", committed)
    try:
        row = write_audit_event(
            owner_session,
            AuditEventInput(
                actor_user_id=actor.id,
                action="employee.update",
                entity_type="employee",
                entity_id=uuid.uuid4(),
                change_source="user",
                metadata={
                    "request_id": str(uuid.uuid4()),
                    "changed_fields": ["department_id", "joining_date"],
                    "outcome": "success",
                },
            ),
        )
    finally:
        event.remove(connection, "before_cursor_execute", capture)
        event.remove(owner_session, "after_commit", committed)

    assert isinstance(row.id, UUID)
    assert row.actor_user_id == actor.id
    assert row.occurred_at is not None and row.occurred_at.tzinfo is not None
    assert row.event_metadata["outcome"] == "success"
    assert len(statements) == 1
    assert "RETURNING PUBLIC.AUDIT_EVENTS.OCCURRED_AT" in re.sub(
        r"\s+", " ", statements[0]
    ).upper()
    assert commits == []
    assert owner_session.get(AuditEvent, row.id) is not None
    assert _read_owner_count(
        owner_engine,
        "SELECT count(*) FROM public.audit_events WHERE id=:id",
        {"id": row.id},
    ) == 0


def test_database_generates_uuid_and_timestamp_if_omitted(owner_session: Session) -> None:
    row = owner_session.execute(
        text(
            "INSERT INTO public.audit_events "
            "(action, entity_type, entity_id, change_source, metadata) "
            "VALUES ('audit.test', 'test_entity', :id, 'system', '{}'::jsonb) "
            "RETURNING id, occurred_at"
        ),
        {"id": uuid.uuid4()},
    ).one()
    assert isinstance(row.id, UUID)
    assert row.occurred_at is not None and row.occurred_at.tzinfo is not None


@pytest.mark.parametrize(
    ("overrides", "state", "constraint"),
    [
        ({"action": None}, "23502", ""),
        ({"action": " "}, "23514", "ck_audit_events_action_nonempty"),
        ({"entity_type": " "}, "23514", "ck_audit_events_entity_type_nonempty"),
        ({"actor_user_id": uuid.uuid4()}, "23503", "fk_audit_events_actor_user_id_users"),
        ({"actor_user_id": None, "change_source": "user"}, "23514", "ck_audit_events_user_actor"),
        ({"change_source": "unknown"}, "23514", "ck_audit_events_change_source"),
    ],
)
def test_audit_constraints_reject_invalid_fields(
    owner_session: Session,
    overrides: dict[str, object],
    state: str,
    constraint: str,
) -> None:
    _expect_error(
        owner_session, INSERT_AUDIT, _values(**overrides), state, constraint
    )


@pytest.mark.parametrize(
    "metadata",
    [
        "null",
        "[]",
        '{"unsupported":"value"}',
        '{"request_id":"not-a-uuid"}',
        '{"request_id":{"nested":"value"}}',
        '{"changed_fields":"department_id"}',
        '{"changed_fields":[1]}',
        '{"changed_fields":["BadName"]}',
        '{"changed_fields":["department_id","department_id"]}',
        json.dumps({"changed_fields": [f"field_{i}" for i in range(21)]}),
        '{"changed_fields":["access_token"]}',
        '{"outcome":{"nested":"value"}}',
        '{"outcome":"pending"}',
    ],
)
def test_database_metadata_constraint_rejects_invalid_metadata(
    owner_session: Session, metadata: str
) -> None:
    _expect_error(
        owner_session,
        INSERT_AUDIT,
        _values(metadata=metadata),
        "23514",
        "ck_audit_events_metadata_valid",
    )


@pytest.mark.parametrize("source", ["system", "import"])
def test_system_and_import_events_allow_null_actor(
    owner_session: Session, source: str
) -> None:
    row = write_audit_event(
        owner_session,
        AuditEventInput(
            actor_user_id=None,
            action="asset.import",
            entity_type="asset",
            entity_id=uuid.uuid4(),
            change_source=source,
        ),
    )
    assert row.id is not None


def test_actor_deletion_is_restricted(owner_session: Session) -> None:
    actor = _actor(owner_session)
    row = write_audit_event(
        owner_session,
        AuditEventInput(
            actor_user_id=actor.id,
            action="employee.update",
            entity_type="employee",
            entity_id=uuid.uuid4(),
            change_source="user",
        ),
    )
    _expect_error(
        owner_session,
        "DELETE FROM public.users WHERE id=:id",
        {"id": actor.id},
        "23001",
        "fk_audit_events_actor_user_id_users",
    )
    assert owner_session.get(AuditEvent, row.id) is not None


def test_audit_mutation_triggers_reject_update_delete_and_truncate(
    owner_session: Session,
) -> None:
    row = write_audit_event(
        owner_session,
        AuditEventInput(
            actor_user_id=None,
            action="audit.probe",
            entity_type="audit_event",
            entity_id=uuid.uuid4(),
            change_source="system",
        ),
    )
    for sql in (
        "UPDATE public.audit_events SET action='audit.changed' WHERE id=:id",
        "DELETE FROM public.audit_events WHERE id=:id",
        "TRUNCATE TABLE public.audit_events",
    ):
        _expect_error(owner_session, sql, {"id": row.id}, "55000")
    assert owner_session.get(AuditEvent, row.id) is not None
