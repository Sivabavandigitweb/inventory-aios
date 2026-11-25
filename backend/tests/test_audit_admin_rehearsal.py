"""Opt-in administrator rehearsal; never commit grants or test data."""
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.services.audit import AuditEventInput, write_audit_event

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get("INVENTORY_ADMIN_AUDIT_REHEARSAL") != "1",
    reason="Explicit administrator rehearsal opt-in required.",
)]


def snapshot(conn):
    queries = [
        "SELECT * FROM pg_auth_members ORDER BY oid",
        "SELECT * FROM pg_roles WHERE rolname LIKE 'inventory_aios_%' ORDER BY oid",
        "SELECT * FROM pg_database WHERE datname=current_database()",
        "SELECT * FROM pg_namespace WHERE nspname='public'",
        "SELECT * FROM pg_default_acl ORDER BY oid",
    ]
    for catalog, namespace in (("pg_class", "relnamespace"), ("pg_proc", "pronamespace"),
                               ("pg_constraint", "connamespace")):
        queries.append(f"SELECT * FROM {catalog} WHERE {namespace}="
                       "'public'::regnamespace ORDER BY oid")
    queries.extend([
        "SELECT a.* FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
        "WHERE c.relnamespace='public'::regnamespace ORDER BY a.attrelid,a.attnum",
        "SELECT t.* FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
        "WHERE c.relnamespace='public'::regnamespace ORDER BY t.oid",
    ])
    result = [list(conn.execute(text(q))) for q in queries]
    for name in conn.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1"
    )).scalars().all():
        quoted = conn.dialect.identifier_preparer.quote(name)
        result.append(list(conn.execute(text(
            f"SELECT md5(row_to_json(t)::text) FROM public.{quoted} t ORDER BY 1"
        ))))
    return result


def denied(conn, sql, state="42501", constraint=None, params=None):
    with pytest.raises(DBAPIError) as error:
        with conn.begin_nested():
            conn.execute(text(sql), params or {})
    assert error.value.orig.sqlstate == state
    if constraint:
        assert error.value.orig.diag.constraint_name == constraint


def test_actual_runtime_writer_with_administrator_rollback():
    engine = create_engine(
        "postgresql+psycopg://postgres@localhost:5432/inventory_aios_restore_check",
        poolclass=NullPool, hide_parameters=True, connect_args={"connect_timeout": 5},
    )
    try:
        with engine.connect() as conn:
            outer = conn.begin()
            baseline = None

            def forbid_commit(connection):
                raise AssertionError("Outer transaction must never commit")

            event.listen(conn, "commit", forbid_commit)
            try:
                assert conn.execute(text(
                    "SELECT current_database(),session_user,current_user,inet_server_port()"
                )).one() == ("inventory_aios_restore_check", "postgres", "postgres", 5432)
                assert conn.execute(text("SELECT version_num FROM public.alembic_version" )
                                    ).scalar_one() == "7d4a9c2e1b60"
                assert conn.execute(text("SELECT pg_get_userbyid(datdba) FROM pg_database "
                                         "WHERE datname=current_database()")
                                    ).scalar_one() == "inventory_aios_owner"
                assert conn.execute(text("SELECT count(*) FROM public.audit_events")
                                    ).scalar_one() == 0
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                    assert not conn.execute(text("SELECT has_table_privilege("
                        "'inventory_aios_app','public.audit_events',:p)"),
                        {"p": privilege}).scalar_one()
                assert not conn.execute(text("SELECT has_any_column_privilege("
                    "'inventory_aios_app','public.audit_events','SELECT') OR has_function_privilege("
                    "'inventory_aios_app','public.inventory_aios_audit_metadata_is_valid(jsonb)',"
                    "'EXECUTE')")).scalar_one()
                baseline = snapshot(conn)
                actor = uuid.uuid4()
                conn.execute(text("INSERT INTO public.users "
                    "(id,username,email,display_name,status) "
                    "VALUES (:id,:name,:email,'Rehearsal Actor','active')"),
                    {"id": actor, "name": f"TEST_ADMIN_{actor.hex}",
                     "email": f"{actor.hex}@example.invalid"})
                # Exercise the real script body with its migrator/owner identity guards.
                # Only the outer psql transaction wrapper is removed; this connection owns rollback.
                script = (Path(__file__).resolve().parents[2] / "scripts/database/"
                          "06_post_audit_migration_grants.sql").read_text()
                prefix = "\\set ON_ERROR_STOP on\nBEGIN;\n"
                assert script.startswith(prefix) and script.rstrip().endswith("COMMIT;")
                assert script.count("COMMIT;") == 1
                body = script[len(prefix):].rstrip().removesuffix("COMMIT;")
                conn.execute(text("SET LOCAL SESSION AUTHORIZATION inventory_aios_migrator"))
                conn.exec_driver_sql(body)
                conn.execute(text("RESET ROLE"))
                conn.execute(text("SET LOCAL SESSION AUTHORIZATION DEFAULT"))
                conn.execute(text("SET LOCAL ROLE inventory_aios_app"))
                assert conn.execute(text("SELECT session_user,current_user")).one() == (
                    "postgres", "inventory_aios_app")
                statements = []

                def capture(connection, cursor, statement, parameters, context, executemany):
                    statements.append(statement)

                event.listen(conn, "before_cursor_execute", capture)
                try:
                    with Session(bind=conn, join_transaction_mode="create_savepoint",
                                 expire_on_commit=False) as session:
                        row = write_audit_event(session, AuditEventInput(
                            actor_user_id=actor, action="employee.update", entity_type="employee",
                            entity_id=uuid.uuid4(), metadata={"request_id": str(uuid.uuid4()),
                            "changed_fields": ["department_id"], "outcome": "success"},
                        ))
                        assert isinstance(row.id, uuid.UUID)
                        assert row.occurred_at is not None and row.occurred_at.tzinfo is not None
                        assert any("RETURNING public.audit_events.occurred_at" in s
                                   for s in statements)
                        session.commit()  # Releases only the Session's savepoint.
                        assert outer.is_active
                finally:
                    event.remove(conn, "before_cursor_execute", capture)
                insert = ("INSERT INTO public.audit_events "
                    "(actor_user_id,action,entity_type,entity_id,change_source,metadata) "
                    "VALUES (:actor,'audit.test','employee',:entity,'user',CAST(:metadata AS jsonb))")
                denied(conn, insert, "23503", "fk_audit_events_actor_user_id_users",
                       {"actor": uuid.uuid4(), "entity": uuid.uuid4(), "metadata": "{}"})
                denied(conn, insert, "23514", "ck_audit_events_metadata_valid",
                       {"actor": actor, "entity": uuid.uuid4(),
                        "metadata": '{"unsupported":"value"}'})
                for sql in (
                    "SELECT id FROM public.audit_events", "SELECT * FROM public.audit_events",
                    "SELECT metadata FROM public.audit_events",
                    "UPDATE public.audit_events SET action='changed'",
                    "DELETE FROM public.audit_events", "TRUNCATE public.audit_events",
                    "ALTER TABLE public.audit_events DISABLE TRIGGER ALL",
                    "ALTER TABLE public.audit_events ADD COLUMN rehearsal_probe integer",
                    "DROP TABLE public.audit_events",
                ):
                    denied(conn, sql)
                denied(conn, "INSERT INTO public.audit_events "
                       "(action,entity_type,entity_id,change_source,occurred_at) VALUES "
                       "('audit.test','employee',gen_random_uuid(),'system',now())")
                for sql in (
                    "CREATE TABLE public.rehearsal_probe (id integer)",
                    "CREATE SCHEMA rehearsal_probe",
                    "CREATE TEMP TABLE rehearsal_probe (id integer)",
                ):
                    denied(conn, sql)
                conn.execute(text("RESET ROLE"))
                assert conn.execute(text("SELECT count(*) FROM public.audit_events")
                                    ).scalar_one() == 1
            finally:
                outer.rollback()
                event.remove(conn, "commit", forbid_commit)
                if baseline is not None:
                    try:
                        conn.execute(text("SET TRANSACTION READ ONLY"))
                        assert conn.execute(text("SELECT session_user,current_user")).one() == (
                            "postgres", "postgres")
                        assert snapshot(conn) == baseline
                    finally:
                        conn.rollback()
    finally:
        engine.dispose()
