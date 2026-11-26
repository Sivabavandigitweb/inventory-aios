from sqlalchemy import LargeBinary, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateTable

from app.models import AuthSession, Base, UserPasswordCredential


def test_authentication_models_register_only_the_approved_public_tables() -> None:
    assert "public.user_password_credentials" in Base.metadata.tables
    assert "public.auth_sessions" in Base.metadata.tables
    assert Base.metadata.tables["public.user_password_credentials"].schema == "public"
    assert Base.metadata.tables["public.auth_sessions"].schema == "public"


def test_credential_model_reuses_user_identity_and_protects_hash_representation() -> None:
    table = UserPasswordCredential.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}

    assert tuple(column.name for column in table.primary_key.columns) == ("user_id",)
    assert table.c.password_hash.type.__class__ is Text
    assert table.c.password_hash.nullable is False
    assert table.c.password_changed_at.type.timezone is True
    assert table.c.created_at.type.timezone is True
    assert table.c.updated_at.type.timezone is True
    assert table.c.credential_version.default.arg == 1
    assert table.c.credential_version.server_default.arg.text == "1"
    assert "ck_user_password_credentials_version_positive" in constraints
    user_fk = next(iter(table.c.user_id.foreign_keys))
    assert user_fk.target_fullname == "users.id"
    assert user_fk.ondelete == "RESTRICT"
    assert set(table.c.keys()) == {
        "user_id", "password_hash", "password_changed_at", "credential_version",
        "created_at", "updated_at",
    }

    marker = "$argon2id$v=19$fictional-test-hash"
    assert marker not in repr(UserPasswordCredential(user_id=None, password_hash=marker))


def test_session_model_stores_only_a_fixed_length_digest_and_supports_multiple_sessions() -> None:
    table = AuthSession.__table__
    constraints = {constraint.name: constraint for constraint in table.constraints}
    indexes = {index.name: tuple(column.name for column in index.columns) for index in table.indexes}

    assert table.c.id.primary_key
    assert table.c.id.type.as_uuid is True
    assert isinstance(table.c.token_hash.type, LargeBinary)
    assert table.c.token_hash.type.length == 32
    assert table.c.token_hash.unique is not True
    user_fk = next(iter(table.c.user_id.foreign_keys))
    assert user_fk.target_fullname == "users.id"
    assert user_fk.ondelete == "RESTRICT"
    assert table.c.credential_version.nullable is False
    assert table.c.revoked_at.nullable is True
    assert all(table.c[name].type.timezone for name in (
        "created_at", "last_seen_at", "expires_at", "revoked_at"
    ))
    assert {
        "uq_auth_sessions_token_hash",
        "ck_auth_sessions_token_hash_length",
        "ck_auth_sessions_credential_version_positive",
        "ck_auth_sessions_last_seen_after_creation",
        "ck_auth_sessions_expiry_after_creation",
    }.issubset(constraints)
    assert indexes == {
        "ix_auth_sessions_user_revoked": ("user_id", "revoked_at"),
        "ix_auth_sessions_expires_at": ("expires_at",),
    }
    assert not any(column.unique for column in table.columns if column.name == "user_id")
    assert "raw_token" not in table.c and "token" not in table.c

    marker = b"fictional-session-digest-not-a-secret"
    assert marker.decode() not in repr(AuthSession(token_hash=marker))


def test_authentication_relationships_and_postgresql_ddl_compile_offline() -> None:
    configure_mappers()
    dialect = postgresql.dialect()
    credential_ddl = str(CreateTable(UserPasswordCredential.__table__).compile(dialect=dialect))
    session_ddl = str(CreateTable(AuthSession.__table__).compile(dialect=dialect))

    assert "CREATE TABLE public.user_password_credentials" in credential_ddl
    assert "CREATE TABLE public.auth_sessions" in session_ddl
    assert "password_hash TEXT NOT NULL" in credential_ddl
    assert "token_hash BYTEA NOT NULL" in session_ddl
    assert "octet_length(token_hash) = 32" in session_ddl
    assert "expires_at > created_at" in session_ddl
