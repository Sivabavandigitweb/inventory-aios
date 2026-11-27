from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.core.sessions import (
    ActivityUpdateResult,
    NewSessionRecord,
    SessionCreationStateChanged,
    SessionRevocationResult,
    SessionTokenDigestCollision,
)
from app.db.auth_repositories import (
    SqlAlchemyAccountSessionStateRepository,
    SqlAlchemyPasswordCredentialRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserIdentityRepository,
)
from app.models import User


def test_user_lookup_uses_injected_username_predicate_and_limits_ambiguity() -> None:
    session = MagicMock()
    session.execute.return_value.all.return_value = [
        SimpleNamespace(id=uuid4(), username="One", status="active")
    ]
    repository = SqlAlchemyUserIdentityRepository(
        session, username_predicate=lambda key: User.username == key
    )
    matches = repository.find_by_canonical_username("one")
    assert len(matches) == 1 and matches[0].username == "One"
    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "LIMIT" in sql and "users.username" in sql


def test_credential_and_account_repositories_return_minimal_projections() -> None:
    user_id = uuid4()
    session = MagicMock()
    session.execute.return_value.one_or_none.return_value = SimpleNamespace(
        user_id=user_id, password_hash="fictional-phc", credential_version=2
    )
    credential = SqlAlchemyPasswordCredentialRepository(session).get_for_user(user_id)
    assert credential.user_id == user_id and credential.credential_version == 2
    assert "fictional-phc" not in repr(credential)

    session.execute.return_value.one_or_none.return_value = SimpleNamespace(
        id=user_id, status="active", credential_version=2
    )
    state = SqlAlchemyAccountSessionStateRepository(session).get_current_state(user_id)
    assert (state.user_id, state.status, state.credential_version) == (user_id, "active", 2)


def make_record():
    now = datetime(2026, 11, 27, tzinfo=UTC)
    return NewSessionRecord(
        session_id=uuid4(), user_id=uuid4(), token_digest=b"x" * 32,
        credential_version=3, created_at=now, last_seen_at=now,
        expires_at=now + timedelta(hours=1),
    )


def clean_session_mock():
    session = MagicMock()
    session.new = []
    session.dirty = []
    session.deleted = []
    return session


def test_session_insert_is_conditional_atomic_ddl_and_commits_only_its_clean_session() -> None:
    session = clean_session_mock()
    record = make_record()
    session.execute.return_value.scalar_one_or_none.return_value = record.session_id
    SqlAlchemySessionRepository(session).create_if_current(record)
    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "INSERT INTO public.auth_sessions" in sql
    assert "SELECT" in sql and "users.status" in sql and "user_password_credentials.credential_version" in sql
    compiled = session.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "active" in compiled.params.values()
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


def test_session_insert_rejects_stale_account_and_digest_collision_without_false_success() -> None:
    session = clean_session_mock()
    session.execute.return_value.scalar_one_or_none.return_value = None
    with pytest.raises(SessionCreationStateChanged):
        SqlAlchemySessionRepository(session).create_if_current(make_record())
    session.commit.assert_not_called()

    collision = IntegrityError("statement", {}, SimpleNamespace(diag=SimpleNamespace(constraint_name="uq_auth_sessions_token_hash")))
    session = clean_session_mock()
    session.execute.side_effect = collision
    with pytest.raises(SessionTokenDigestCollision):
        SqlAlchemySessionRepository(session).create_if_current(make_record())
    session.commit.assert_not_called()


def test_activity_update_is_conditional_and_never_extends_absolute_expiry() -> None:
    session = clean_session_mock()
    session.execute.return_value.scalar_one_or_none.return_value = uuid4()
    now = datetime(2026, 11, 27, tzinfo=UTC)
    outcome = SqlAlchemySessionRepository(session).update_activity_if_current(
        session_id=uuid4(), expected_user_id=uuid4(), expected_credential_version=3,
        expected_last_seen_at=now - timedelta(minutes=4), checked_at=now,
        new_last_seen_at=now, inactivity_timeout=timedelta(minutes=30),
    )
    assert outcome is ActivityUpdateResult.UPDATED
    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "auth_sessions.expires_at" in sql and "auth_sessions.revoked_at IS NULL" in sql
    assert "user_password_credentials.credential_version" in sql and "users.status" in sql
    session.commit.assert_called_once()


def test_activity_stale_writer_and_revocation_are_safe_and_idempotent() -> None:
    session = clean_session_mock()
    now = datetime(2026, 11, 27, tzinfo=UTC)
    session.execute.return_value.scalar_one_or_none.return_value = None
    session.execute.return_value.one_or_none.return_value = SimpleNamespace(
        user_id=uuid4(), credential_version=2,
        last_seen_at=now - timedelta(minutes=1), expires_at=now + timedelta(hours=1),
        revoked_at=None,
    )
    repo = SqlAlchemySessionRepository(session)
    assert repo.update_activity_if_current(
        session_id=uuid4(), expected_user_id=session.execute.return_value.one_or_none.return_value.user_id,
        expected_credential_version=2, expected_last_seen_at=now - timedelta(minutes=2),
        checked_at=now, new_last_seen_at=now, inactivity_timeout=timedelta(minutes=30),
    ) is ActivityUpdateResult.ALREADY_ADVANCED
    session.commit.assert_not_called()

    session.execute.return_value.scalar_one_or_none.return_value = uuid4()
    assert repo.revoke_one_if_active(uuid4(), now) is SessionRevocationResult.REVOKED
    session.commit.assert_called_once()


def test_user_wide_revocation_is_narrowly_scoped_and_committed() -> None:
    session = clean_session_mock()
    session.execute.return_value.all.return_value = [(uuid4(),), (uuid4(),)]
    user_id = uuid4()
    assert SqlAlchemySessionRepository(session).revoke_all_for_user(user_id, datetime.now(UTC)) == 2
    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "auth_sessions.user_id" in sql and "auth_sessions.revoked_at IS NULL" in sql
    session.commit.assert_called_once()
