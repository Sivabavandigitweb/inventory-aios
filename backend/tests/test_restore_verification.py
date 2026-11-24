from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.database.verify_restore import (  # noqa: E402
    archive_not_null_columns,
    build_pg_dump_command,
    constraints_match_archive,
    normalized_statements,
    run_pg_dump_schema,
)


def test_pg_dump_uses_validated_restore_check_identity_and_noninteractive_auth(tmp_path):
    url = make_url("postgresql+psycopg://inventory_aios_app@localhost:5432/inventory_aios_restore_check")

    command = build_pg_dump_command("pg_dump.exe", url, tmp_path / "schema.sql")

    assert command[0] == "pg_dump.exe"
    assert command[command.index("--host") + 1] == "localhost"
    assert command[command.index("--port") + 1] == "5432"
    assert command[command.index("--username") + 1] == "inventory_aios_app"
    assert command[command.index("--dbname") + 1] == "inventory_aios_restore_check"
    assert "--no-password" in command


def test_pg_dump_subprocess_inherits_configured_pgpassfile(monkeypatch, tmp_path):
    pgpassfile = str(tmp_path / "pgpass.conf")
    monkeypatch.setenv("PGPASSFILE", pgpassfile)
    monkeypatch.setenv("PGUSER", "Digit Web")
    run = Mock()
    monkeypatch.setattr("scripts.database.verify_restore.subprocess.run", run)
    url = make_url("postgresql+psycopg://inventory_aios_app@localhost:5432/inventory_aios_restore_check")

    run_pg_dump_schema("pg_dump.exe", url, tmp_path / "schema.sql")

    command = run.call_args.args[0]
    environment = run.call_args.kwargs["env"]
    assert command[command.index("--username") + 1] == "inventory_aios_app"
    assert environment["PGPASSFILE"] == pgpassfile
    assert environment["PGUSER"] == "Digit Web"
    assert command[command.index("--username") + 1] == "inventory_aios_app"
    assert run.call_args.kwargs["check"] is True


def test_pg_dump_authentication_failure_is_clear_and_does_not_leak_output(monkeypatch, tmp_path):
    failure = subprocess.CalledProcessError(1, "pg_dump", stderr="password detail must not be shown")
    monkeypatch.setattr("scripts.database.verify_restore.subprocess.run", Mock(side_effect=failure))
    url = make_url("postgresql+psycopg://inventory_aios_app@localhost:5432/inventory_aios_restore_check")

    with pytest.raises(RuntimeError, match="secured PGPASSFILE") as error:
        run_pg_dump_schema("pg_dump.exe", url, tmp_path / "schema.sql")

    assert "password detail" not in str(error.value)


def test_pg_dump_rejects_password_in_database_url(tmp_path):
    url = make_url("postgresql+psycopg://inventory_aios_app:secret@localhost:5432/inventory_aios_restore_check")

    with pytest.raises(RuntimeError, match="passwords must be supplied"):
        build_pg_dump_command("pg_dump.exe", url, tmp_path / "schema.sql")



def test_postgresql_18_not_null_catalog_entries_are_reconciled_separately():
    archive_not_null = {("employees", "id"), ("employees", "email")}
    catalog_not_null = {("employees", "id"), ("employees", "email")}
    # p/f/u have archive TOC entries; CHECK is inline and n is represented by column NOT NULL.
    catalog_counts = {"p": 1, "f": 1, "u": 1, "c": 1, "n": 2}

    assert constraints_match_archive(catalog_counts, 3, archive_not_null, catalog_not_null)
    assert not constraints_match_archive(catalog_counts, 3, archive_not_null, {("employees", "id")})
    assert not constraints_match_archive({**catalog_counts, "f": 0}, 3, archive_not_null, catalog_not_null)


def test_archive_not_null_parser_excludes_check_expressions_and_string_literals():
    schema = """CREATE TABLE public.employees (
        id uuid NOT NULL,
        email text NOT NULL DEFAULT 'NOT NULL',
        note text,
        CONSTRAINT ck_note CHECK (note IS NOT NULL)
    );"""

    assert archive_not_null_columns(schema) == {("employees", "id"), ("employees", "email")}


def test_schema_normalization_ignores_pg_dump_guards_and_equivalent_check_casts():
    archive = r"""\restrict generated_token
SET statement_timeout = 0;
CREATE TABLE public.items (
  kind character varying NOT NULL,
  CONSTRAINT ck_kind CHECK (((kind)::text = ANY ((ARRAY['individual'::character varying, 'quantity'::character varying])::text[])))
);
\unrestrict generated_token
"""
    live = """CREATE TABLE public.items (
  kind character varying NOT NULL,
  CONSTRAINT ck_kind CHECK (((kind)::text = ANY (ARRAY[('individual'::character varying)::text, ('quantity'::character varying)::text])))
);"""

    assert normalized_statements(archive) == normalized_statements(live)


@pytest.mark.parametrize(
    ("archive", "live"),
    [
        ("CREATE TABLE public.t (value integer DEFAULT 1 NOT NULL);", "CREATE TABLE public.t (value bigint DEFAULT 1 NOT NULL);"),
        ("CREATE TABLE public.t (value integer DEFAULT 1 NOT NULL);", "CREATE TABLE public.t (value integer DEFAULT 2 NOT NULL);"),
        (
            "CREATE TABLE public.items (kind character varying, CONSTRAINT ck_kind CHECK (kind::text = ANY ((ARRAY['individual'::character varying, 'quantity'::character varying])::text[])));",
            "CREATE TABLE public.items (kind character varying, CONSTRAINT ck_kind CHECK (kind::text = ANY (ARRAY[('individual'::character varying)::text, ('bulk'::character varying)::text])));",
        ),
        (
            "ALTER TABLE ONLY public.child ADD CONSTRAINT fk_parent FOREIGN KEY (parent_id) REFERENCES public.parent(id) ON DELETE RESTRICT;",
            "ALTER TABLE ONLY public.child ADD CONSTRAINT fk_parent FOREIGN KEY (parent_id) REFERENCES public.parent(id) ON DELETE CASCADE;",
        ),
    ],
)
def test_schema_normalization_detects_meaningful_type_default_and_fk_changes(archive, live):
    assert normalized_statements(archive) != normalized_statements(live)
