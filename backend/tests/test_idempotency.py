"""Offline metadata and pure service tests; no PostgreSQL connection is made."""

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.schema import CreateIndex, CreateTable

from app.core.authentication import Principal
from app.core.errors import AppError
from app.models import Base, IdempotencyRequest, User
from app.services.idempotency import StoredRequest, decide_request
from app.services.idempotency_fingerprint import InvalidFingerprintInput, fingerprint_request


@pytest.fixture(autouse=True)
def forbid_database_connections(monkeypatch):
    import psycopg

    def forbidden(*args, **kwargs):
        raise AssertionError("Offline idempotency tests cannot connect to a database")

    monkeypatch.setattr(Engine, "connect", forbidden)
    monkeypatch.setattr(psycopg, "connect", forbidden)


def test_model_registration_constraints_and_indexes():
    table = IdempotencyRequest.__table__
    assert Base.metadata.tables["public.idempotency_requests"] is table
    assert table.schema == "public"
    assert list(table.primary_key.columns.keys()) == ["id"]
    assert str(table.c.id.server_default.arg) == "gen_random_uuid()"
    assert table.c.id.default is not None
    assert table.c.principal_id.nullable is False
    assert table.c.completed_at.nullable is True
    assert table.c.completed_at.type.timezone is True
    assert {"operation_scope", "idempotency_key", "request_fingerprint", "status"} <= set(
        table.c.keys()
    )
    for forbidden in ("request_body", "response_body", "expires_at", "error_code", "token"):
        assert forbidden not in table.c
    unique = next(c for c in table.constraints if isinstance(c, UniqueConstraint))
    assert unique.name == "uq_idempotency_requests_principal_scope_key"
    assert tuple(unique.columns.keys()) == (
        "principal_id", "operation_scope", "idempotency_key"
    )
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert {"ck_idempotency_requests_scope_nonempty", "ck_idempotency_requests_key_nonempty",
            "ck_idempotency_requests_fingerprint_sha256", "ck_idempotency_requests_status",
            "ck_idempotency_requests_completion", "ck_idempotency_requests_resource_pair"} == set(checks)
    assert "response_status BETWEEN 200 AND 299" in checks["ck_idempotency_requests_completion"]
    assert "response_status IS NOT NULL" in checks["ck_idempotency_requests_completion"]
    assert {i.name: tuple(i.columns.keys()) for i in table.indexes} == {
        "ix_idempotency_requests_principal_status": ("principal_id", "status")
    }


def test_foreign_key_and_relationship_reuse_existing_user_model():
    configure_mappers()
    table = IdempotencyRequest.__table__
    foreign_key, = table.c.principal_id.foreign_keys
    assert foreign_key.column is User.__table__.c.id
    assert foreign_key.ondelete == "RESTRICT"
    assert foreign_key.constraint.name == "fk_idempotency_requests_principal_id_users"
    assert inspect(IdempotencyRequest).relationships.principal.mapper.class_ is User
    assert "delete" not in inspect(IdempotencyRequest).relationships.principal.cascade
    assert "public.users" not in Base.metadata.tables


def test_postgresql_ddl_compiles_without_a_connection():
    table = IdempotencyRequest.__table__
    dialect = postgresql.dialect()
    ddl = str(CreateTable(table).compile(dialect=dialect))
    assert "CREATE TABLE public.idempotency_requests" in ddl
    assert "UUID DEFAULT gen_random_uuid() NOT NULL" in ddl
    assert "UNIQUE (principal_id, operation_scope, idempotency_key)" in ddl
    assert "TIMESTAMP WITH TIME ZONE" in ddl
    assert "ON DELETE RESTRICT" in ddl
    index, = table.indexes
    assert "ON public.idempotency_requests" in str(CreateIndex(index).compile(dialect=dialect))
    qualified = str(CreateTable(table).compile(
        dialect=dialect, schema_translate_map={None: "public"}, render_schema_translate=True
    ))
    assert "REFERENCES public.users (id)" in qualified


def test_fingerprint_is_stable_for_supported_equivalent_values():
    ident = uuid.uuid4()
    left = {"b": [Decimal("1.00"), ident], "a": {
        "date": date(2026, 11, 24),
        "time": datetime(2026, 11, 24, 10, tzinfo=timezone.utc),
    }}
    right = {"a": {"time": datetime(2026, 11, 24, 15, 30,
                         tzinfo=timezone(timedelta(hours=5, minutes=30))),
                   "date": date(2026, 11, 24)},
             "b": [Decimal("1.0"), ident]}
    assert fingerprint_request("v1:POST:/api/v1/receipts", left) == fingerprint_request(
        "v1:POST:/api/v1/receipts", right
    )
    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint_request("v1:POST:/api/v1/receipts", left))


@pytest.mark.parametrize("changed", [
    {"value": "1"}, {"value": 1}, {"value": True}, {"value": [1, 2]},
    {"value": None}, {"other": Decimal("1")},
])
def test_fingerprint_distinguishes_meaningful_changes(changed):
    baseline = fingerprint_request("v1:POST:/receipts", {"value": Decimal("1")})
    assert fingerprint_request("v1:POST:/receipts", changed) != baseline
    assert fingerprint_request("v2:POST:/receipts", {"value": Decimal("1")}) != baseline
    assert fingerprint_request("v1:POST:/receipts", {"value": [2, 1]}) != fingerprint_request(
        "v1:POST:/receipts", {"value": [1, 2]}
    )


@pytest.mark.parametrize("payload", [
    {"password": "SENSITIVE-VALUE"}, {"api_key": "SENSITIVE-VALUE"},
    {"nested": {"access_token": "SENSITIVE-VALUE"}},
    {"value": b"SENSITIVE-VALUE"}, {"value": 1.5},
    {"value": datetime(2026, 11, 24)}, {"value": Decimal("NaN")},
    {42: "SENSITIVE-VALUE"},
])
def test_fingerprint_rejects_unsafe_or_unsupported_data_without_leaking(payload, caplog):
    with pytest.raises(InvalidFingerprintInput) as error:
        fingerprint_request("v1:POST:/receipts", payload)
    assert "SENSITIVE-VALUE" not in str(error.value)
    assert "SENSITIVE-VALUE" not in caplog.text


def test_high_precision_decimal_values_remain_distinct():
    first = Decimal("1.1234567890123456789012345678901")
    second = Decimal("1.1234567890123456789012345678902")
    assert fingerprint_request("v1:POST:/receipts", {"value": first}) != fingerprint_request(
        "v1:POST:/receipts", {"value": second}
    )


def test_fingerprint_rejects_cycles_and_bad_scope():
    payload = {}
    payload["nested"] = payload
    with pytest.raises(InvalidFingerprintInput):
        fingerprint_request("v1:POST:/receipts", payload)
    with pytest.raises(InvalidFingerprintInput):
        fingerprint_request("", {"name": "safe"})


@pytest.fixture
def request_context():
    principal = Principal(user_id=uuid.uuid4(), permissions=frozenset({"receipts:create"}))
    scope = "v1:POST:/api/v1/receipts"
    key = "request-1"
    digest = fingerprint_request(scope, {"quantity": 1})
    return principal, scope, key, digest


def test_first_request_authorizes_and_proposes_execution_without_io(request_context, monkeypatch):
    principal, scope, key, digest = request_context
    events = []

    def no_commit(*args, **kwargs):
        raise AssertionError("Service must not commit")

    monkeypatch.setattr(Session, "commit", no_commit)
    result = decide_request(
        principal=principal, operation_scope=scope, idempotency_key=key,
        request_fingerprint=digest, existing=None,
        authorize_operation=lambda p, s: events.append((p.user_id, s)),
        authorize_result=lambda *args: pytest.fail("No result exists"),
    )
    assert result.kind == "execute" and result.response_status is None
    assert events == [(principal.user_id, scope)]


def test_replay_rechecks_operation_and_result_authorization(request_context):
    principal, scope, key, digest = request_context
    resource_id = uuid.uuid4()
    stored = StoredRequest(principal.user_id, scope, key, digest, "succeeded", 201,
                           "receipt", resource_id)
    events = []
    result = decide_request(
        principal=principal, operation_scope=scope, idempotency_key=key,
        request_fingerprint=digest, existing=stored,
        authorize_operation=lambda p, s: events.append("operation"),
        authorize_result=lambda p, t, i: events.append((p.user_id, t, i)),
    )
    assert result.kind == "replay" and result.response_status == 201
    assert result.resource_type == "receipt" and result.resource_id == resource_id
    assert events == ["operation", (principal.user_id, "receipt", resource_id)]


def test_revoked_access_blocks_replay_before_fingerprint_conflict(request_context):
    principal, scope, key, digest = request_context
    stored = StoredRequest(principal.user_id, scope, key, digest, "succeeded", 201,
                           "receipt", uuid.uuid4())
    bad_digest = fingerprint_request(scope, {"quantity": 2})

    def denied(*args):
        raise AppError("FORBIDDEN", "This operation is not permitted.", 403)

    with pytest.raises(AppError) as error:
        decide_request(
            principal=principal, operation_scope=scope, idempotency_key=key,
            request_fingerprint=bad_digest, existing=stored,
            authorize_operation=lambda *args: None, authorize_result=denied,
        )
    assert error.value.status_code == 403
    with pytest.raises(AppError) as operation_error:
        decide_request(
            principal=principal, operation_scope=scope, idempotency_key=key,
            request_fingerprint=digest, existing=stored,
            authorize_operation=denied, authorize_result=lambda *args: None,
        )
    assert operation_error.value.status_code == 403


def test_conflict_and_cross_principal_do_not_expose_stored_data(request_context):
    principal, scope, key, digest = request_context
    stored = StoredRequest(principal.user_id, scope, key, digest, "succeeded", 201,
                           "receipt", uuid.uuid4())
    bad_digest = fingerprint_request(scope, {"quantity": 2})
    with pytest.raises(AppError) as conflict:
        decide_request(
            principal=principal, operation_scope=scope, idempotency_key=key,
            request_fingerprint=bad_digest, existing=stored,
            authorize_operation=lambda *args: None, authorize_result=lambda *args: None,
        )
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    assert digest not in str(conflict.value)
    other = Principal(uuid.uuid4(), frozenset({"receipts:create"}))
    with pytest.raises(AppError) as cross_user:
        decide_request(
            principal=other, operation_scope=scope, idempotency_key=key,
            request_fingerprint=digest, existing=stored,
            authorize_operation=lambda *args: None,
            authorize_result=lambda *args: pytest.fail("Cross-user result was exposed"),
        )
    assert cross_user.value.code == "IDEMPOTENCY_UNAVAILABLE"
    assert cross_user.value.status_code == 404


def test_in_progress_and_malformed_success_fail_closed(request_context):
    principal, scope, key, digest = request_context
    stored = StoredRequest(principal.user_id, scope, key, digest, "processing")
    with pytest.raises(AppError) as in_progress:
        decide_request(
            principal=principal, operation_scope=scope, idempotency_key=key,
            request_fingerprint=digest, existing=stored,
            authorize_operation=lambda *args: None, authorize_result=lambda *args: None,
        )
    assert in_progress.value.code == "IDEMPOTENCY_IN_PROGRESS"
    for malformed in (
        StoredRequest(principal.user_id, scope, key, digest, "succeeded", 500),
        StoredRequest(principal.user_id, scope, key, "invalid", "succeeded", 201),
        StoredRequest(principal.user_id, scope, key, digest, "succeeded", 201, "receipt"),
    ):
        with pytest.raises(AppError) as unavailable:
            decide_request(
                principal=principal, operation_scope=scope, idempotency_key=key,
                request_fingerprint=digest, existing=malformed,
                authorize_operation=lambda *args: None, authorize_result=lambda *args: None,
            )
        assert unavailable.value.status_code == 503


def test_no_live_runner_or_migration_was_added():
    root = Path(__file__).parents[1]
    assert not (root / "app" / "services" / "idempotency_runner.py").exists()
    assert set(path.name for path in (root / "alembic" / "versions").glob("*.py")) == {
        "36368303c6c6_create_core_foundation_tables.py",
        "7d4a9c2e1b60_add_append_only_audit_events.py",
    }
