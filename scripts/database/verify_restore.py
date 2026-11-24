"""Read-only backup/restore comparison. Prints metadata and row counts only."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_integration_test_settings  # noqa: E402
from app.core.integration_test_config import require_isolated_test_url  # noqa: E402

EXPECTED_REVISION = "36368303c6c6"
EXPECTED = {"tables": 12, "explicit_indexes": 8, "functions": 2, "triggers": 11}
COPY_START = re.compile(r"^COPY\s+(?:public\.)?([^\s(]+)\s*\(.*\)\s+FROM\s+stdin;$", re.IGNORECASE)

RESTRICT_DIRECTIVE = re.compile(r"(?m)^\s*\\(?:un)?restrict\s+\S+\s*$")
PUBLIC_CONSTRAINT_TOC = re.compile(r"\b(?:FK\s+)?CONSTRAINT\s+public\s+", re.IGNORECASE)
CREATE_PUBLIC_TABLE = re.compile(
    r'\bCREATE\s+TABLE\s+(?:ONLY\s+)?(?:"public"|public)\.("(?:""|[^"])+"|[A-Za-z_][A-Za-z_0-9$]*)\s*\(',
    re.IGNORECASE,
)
TABLE_CONSTRAINT_START = re.compile(
    r'^\s*(?:CONSTRAINT\s+(?:"(?:""|[^"])+"|[A-Za-z_][A-Za-z_0-9$]*)\s+)?'
    r'(?:CHECK|PRIMARY\s+KEY|UNIQUE|FOREIGN\s+KEY|EXCLUDE)\b',
    re.IGNORECASE,
)


def normalize_check_casts(statement: str) -> str:
    """Normalize PG deparser's equivalent varchar/text casts only inside CHECK clauses."""
    if not re.search(r"\bCHECK\s*\(", statement, re.IGNORECASE):
        return statement
    statement = re.sub(
        r"\((('(?:''|[^'])*')::character varying)\)::text",
        r"\1",
        statement,
        flags=re.IGNORECASE,
    )
    varchar_literal = r"'(?:''|[^'])*'::character varying"
    varchar_array = rf"(ARRAY\[{varchar_literal}(?:\s*,\s*{varchar_literal})*\])"
    return re.sub(rf"\({varchar_array}\)::text\[\]", r"\1", statement, flags=re.IGNORECASE)


def split_table_definition(body: str) -> list[str]:
    """Split a CREATE TABLE body at top-level commas, respecting SQL quoting."""
    pieces: list[str] = []
    start = depth = 0
    state = "normal"
    i = 0
    while i < len(body):
        ch = body[i]
        if state in {"single", "double"}:
            quote = "'" if state == "single" else '"'
            if ch == quote:
                if i + 1 < len(body) and body[i + 1] == quote:
                    i += 2
                    continue
                state = "normal"
            elif ch == "\\" and state == "single" and i + 1 < len(body):
                i += 2
                continue
        elif ch == "'":
            state = "single"
        elif ch == '"':
            state = "double"
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                raise RuntimeError("Could not parse a CREATE TABLE definition from the backup archive.")
        elif ch == "," and depth == 0:
            pieces.append(body[start:i].strip())
            start = i + 1
        i += 1
    if depth != 0 or state != "normal":
        raise RuntimeError("Could not parse a CREATE TABLE definition from the backup archive.")
    pieces.append(body[start:].strip())
    return [piece for piece in pieces if piece]


def archive_not_null_columns(schema_sql: str) -> set[tuple[str, str]]:
    """Read column NOT NULL declarations from archive CREATE TABLE statements."""
    found: set[tuple[str, str]] = set()
    for statement in normalized_statements(schema_sql):
        match = CREATE_PUBLIC_TABLE.search(statement)
        if not match:
            continue
        table = match.group(1).strip('"').replace('""', '"')
        opening = match.end() - 1
        depth = 0
        state = "normal"
        closing = None
        i = opening
        while i < len(statement):
            ch = statement[i]
            if state in {"single", "double"}:
                quote = "'" if state == "single" else '"'
                if ch == quote:
                    if i + 1 < len(statement) and statement[i + 1] == quote:
                        i += 2
                        continue
                    state = "normal"
                elif ch == "\\" and state == "single" and i + 1 < len(statement):
                    i += 2
                    continue
            elif ch == "'":
                state = "single"
            elif ch == '"':
                state = "double"
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    closing = i
                    break
            i += 1
        if closing is None:
            raise RuntimeError("Could not parse a CREATE TABLE body from the backup archive.")
        for item in split_table_definition(statement[opening + 1 : closing]):
            if TABLE_CONSTRAINT_START.match(item):
                continue
            col = re.match(r'^\s*(?:"((?:""|[^"])*)"|([A-Za-z_][A-Za-z_0-9$]*))', item)
            if not col:
                continue
            column = (col.group(1) or col.group(2)).replace('""', '"')
            without_strings = re.sub(r"'(?:''|[^'])*'", "''", item)
            if re.search(r"\bNOT\s+NULL\b", without_strings, re.IGNORECASE):
                found.add((table, column))
    return found


PG_BIN = Path(r"C:\Program Files\PostgreSQL\18\bin")


def resolve_executable(explicit: str | None, name: str) -> str:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise RuntimeError(f"Configured {name} executable was not found.")
        return str(path.resolve())
    located = shutil.which(name)
    if located:
        return located
    fallback = PG_BIN / f"{name}.exe"
    if fallback.is_file():
        return str(fallback)
    raise RuntimeError(f"Could not locate {name}; add it to PATH or pass its executable path.")



def constraints_match_archive(
    catalog_counts: dict[str, int],
    archive_toc_count: int,
    archive_not_null: set[tuple[str, str]],
    catalog_not_null: set[tuple[str, str]],
) -> bool:
    """Reconcile TOC constraints with catalog types and column nullability separately."""
    listed_types = sum(catalog_counts.get(kind, 0) for kind in ("p", "f", "u"))
    return listed_types == archive_toc_count and archive_not_null == catalog_not_null


def postgres_subprocess_env() -> dict[str, str]:
    """Preserve libpq configuration, including a locally configured PGPASSFILE."""
    return os.environ.copy()


def build_pg_dump_command(executable: str, url, output: Path) -> list[str]:
    """Build a passwordless, noninteractive pg_dump command from the validated URL."""
    if url.password is not None:
        raise RuntimeError("Database passwords must be supplied through secured libpq configuration.")
    return [
        executable,
        "--schema-only",
        "--no-owner",
        "--no-privileges",
        "--no-password",
        "--host",
        url.host,
        "--port",
        str(url.port),
        "--username",
        url.username,
        "--dbname",
        url.database,
        "--file",
        str(output),
    ]


def run_pg_dump_schema(executable: str, url, output: Path) -> None:
    try:
        subprocess.run(
            build_pg_dump_command(executable, url, output),
            check=True,
            env=postgres_subprocess_env(),
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        raise RuntimeError(
            "pg_dump failed without prompting; check the secured PGPASSFILE entry and read access "
            "for inventory_aios_app on inventory_aios_restore_check."
        ) from None


def normalized_statements(source: str) -> list[str]:
    source = RESTRICT_DIRECTIVE.sub("", source)
    out: list[str] = []
    buf: list[str] = []
    i = 0
    state = "normal"
    dollar_tag = ""
    pending_space = False
    while i < len(source):
        ch = source[i]
        if state == "line_comment":
            if ch == "\n":
                state = "normal"
                pending_space = True
            i += 1
            continue
        if state == "block_comment":
            if source.startswith("*/", i):
                state = "normal"
                i += 2
            else:
                i += 1
            continue
        if state == "single" or state == "double":
            buf.append(ch)
            if ch == ("'" if state == "single" else '"'):
                if i + 1 < len(source) and source[i + 1] == ch:
                    buf.append(ch)
                    i += 2
                    continue
                state = "normal"
            elif ch == "\\" and state == "single" and i + 1 < len(source):
                buf.append(source[i + 1])
                i += 2
                continue
            i += 1
            continue
        if state == "dollar":
            if source.startswith(dollar_tag, i):
                buf.append(dollar_tag)
                i += len(dollar_tag)
                state = "normal"
            else:
                buf.append(ch)
                i += 1
            continue
        if source.startswith("--", i):
            state = "line_comment"
            i += 2
            continue
        if source.startswith("/*", i):
            state = "block_comment"
            i += 2
            continue
        if ch == "'":
            if pending_space and buf and not buf[-1].isspace():
                buf.append(" ")
            pending_space = False
            state = "single"
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            if pending_space and buf and not buf[-1].isspace():
                buf.append(" ")
            pending_space = False
            state = "double"
            buf.append(ch)
            i += 1
            continue
        if ch == "$":
            match = re.match(r"\$[A-Za-z_0-9]*\$", source[i:])
            if match:
                dollar_tag = match.group(0)
                if pending_space and buf and not buf[-1].isspace():
                    buf.append(" ")
                pending_space = False
                buf.append(dollar_tag)
                i += len(dollar_tag)
                state = "dollar"
                continue
        if ch == ";":
            statement = "".join(buf).strip()
            if statement and not statement.upper().startswith(("SET ", "SELECT PG_CATALOG.SET_CONFIG")):
                out.append(normalize_check_casts(statement))
            buf.clear()
            pending_space = False
            i += 1
            continue
        if ch.isspace():
            pending_space = True
            i += 1
            continue
        if pending_space and buf and not buf[-1].isspace():
            buf.append(" ")
        pending_space = False
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail and not tail.upper().startswith(("SET ", "SELECT PG_CATALOG.SET_CONFIG")):
        out.append(normalize_check_casts(tail))
    return sorted(out)


def count_archive_rows(archive: Path, pg_restore: str) -> dict[str, int]:
    proc = subprocess.Popen(
        [pg_restore, "--data-only", "--file=-", str(archive)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=postgres_subprocess_env(),
    )
    assert proc.stdout is not None
    counts: dict[str, int] = {}
    active: str | None = None
    for line in proc.stdout:
        if active is None:
            match = COPY_START.match(line.rstrip("\r\n"))
            if match:
                active = match.group(1).strip('"')
                counts[active] = 0
        elif line.rstrip("\r\n") == r"\.":
            active = None
        else:
            counts[active] += 1
    code = proc.wait()
    if code:
        raise RuntimeError("Could not stream table data from the backup archive.")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--pg-restore", help="Explicit pg_restore executable path.")
    parser.add_argument("--pg-dump", help="Explicit pg_dump executable path.")
    args = parser.parse_args()
    archive = args.backup.resolve()
    pg_restore = resolve_executable(args.pg_restore, "pg_restore")
    pg_dump = resolve_executable(args.pg_dump, "pg_dump")
    os.chdir(BACKEND_ROOT)
    if not archive.is_file():
        raise RuntimeError("Backup archive path does not exist.")
    settings = get_integration_test_settings()
    url_string = require_isolated_test_url(settings.database_url)
    url = make_url(url_string)
    if url.password is not None:
        raise RuntimeError("Use a passwordless test URL with a secured PGPASSFILE; credentials are not accepted on command lines.")

    toc = subprocess.run(
        [pg_restore, "--list", str(archive)],
        check=True,
        capture_output=True,
        text=True,
        env=postgres_subprocess_env(),
    ).stdout
    archive_indexes = [line for line in toc.splitlines() if re.search(r"\bINDEX\s+public\s+", line)]
    archive_tables = [line for line in toc.splitlines() if re.search(r"\bTABLE\s+public\s+", line) and "TABLE DATA" not in line]
    archive_constraint_entries = [line for line in toc.splitlines() if PUBLIC_CONSTRAINT_TOC.search(line)]
    archive_rows = count_archive_rows(archive, pg_restore)

    with tempfile.TemporaryDirectory(prefix="inventory-aios-restore-verify-") as temp:
        backup_sql = Path(temp, "backup.sql")
        restore_sql = Path(temp, "restore.sql")
        subprocess.run(
            [pg_restore, "--schema-only", "--no-owner", "--no-acl", "--file", str(backup_sql), str(archive)],
            check=True,
            env=postgres_subprocess_env(),
        )
        run_pg_dump_schema(pg_dump, url, restore_sql)
        backup_schema = backup_sql.read_text(encoding="utf-8", errors="replace")
        restored_schema = restore_sql.read_text(encoding="utf-8", errors="replace")
        schema_matches = normalized_statements(backup_schema) == normalized_statements(restored_schema)
        backup_not_null = archive_not_null_columns(backup_schema)

    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
    try:
        with engine.connect() as conn, conn.begin():
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            identity = conn.execute(text("SELECT current_database(),session_user,current_user,inet_server_port(),current_setting('transaction_read_only')")).one()
            if tuple(identity[:4]) != ("inventory_aios_restore_check", "inventory_aios_app", "inventory_aios_app", 5432) or identity[4] != "on":
                raise RuntimeError("Restore database connection identity did not match the approved read-only target.")
            revision = conn.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one()
            tables = conn.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public' ORDER BY tablename")).scalars().all()
            constraint_counts = dict(conn.execute(text("SELECT contype,count(*) FROM pg_catalog.pg_constraint WHERE connamespace='public'::regnamespace GROUP BY contype")).all())
            restored_not_null = set(conn.execute(text("""SELECT c.relname,a.attname
                FROM pg_catalog.pg_constraint co
                JOIN pg_catalog.pg_class c ON c.oid=co.conrelid
                JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                JOIN LATERAL pg_catalog.unnest(co.conkey) AS k(attnum) ON true
                JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
                WHERE n.nspname='public' AND co.contype='n'""")).all())
            constraints_match = constraints_match_archive(
                constraint_counts,
                len(archive_constraint_entries),
                backup_not_null,
                restored_not_null,
            )
            functions = conn.execute(text("SELECT count(*) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.prokind='f'")).scalar_one()
            triggers = conn.execute(text("SELECT count(*) FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND NOT t.tgisinternal")).scalar_one()
            explicit_indexes = conn.execute(text("SELECT count(*) FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class x ON x.oid=i.indexrelid JOIN pg_catalog.pg_namespace n ON n.oid=x.relnamespace WHERE n.nspname='public' AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint c WHERE c.conindid=i.indexrelid)")).scalar_one()
            restore_rows = {}
            for table in tables:
                qname = conn.dialect.identifier_preparer.quote(table)
                restore_rows[table] = conn.exec_driver_sql(f"SELECT count(*) FROM public.{qname}").scalar_one()
            summary = {"identity": list(identity), "revision": revision, "table_count_including_alembic": len(tables), "catalog_constraint_counts_by_type": {str(key): value for key, value in sorted(constraint_counts.items())}, "archive_listed_constraint_entries": len(archive_constraint_entries), "archive_not_null_columns": len(backup_not_null), "catalog_not_null_constraints": len(restored_not_null), "constraint_comparison_matches": constraints_match, "explicit_index_count_excluding_constraint_indexes": explicit_indexes, "function_count": functions, "trigger_count_excluding_internal": triggers, "archive_table_entries": len(archive_tables), "archive_index_entries": len(archive_indexes), "schema_definitions_match": schema_matches, "backup_row_counts": archive_rows, "restore_row_counts": restore_rows}
            print(json.dumps(summary, sort_keys=True, default=str))
            if revision != EXPECTED_REVISION or len(tables) != EXPECTED["tables"] or explicit_indexes != EXPECTED["explicit_indexes"] or functions != EXPECTED["functions"] or triggers != EXPECTED["triggers"]:
                return 2
            if len(archive_indexes) != EXPECTED["explicit_indexes"] or len(archive_tables) != EXPECTED["tables"]:
                return 2
            if not schema_matches or not constraints_match or archive_rows != restore_rows:
                return 2
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, SQLAlchemyError):
        print("Restore verification failed; inspect the operator-side tool/configuration without exposing credentials.", file=sys.stderr)
        raise SystemExit(1)
