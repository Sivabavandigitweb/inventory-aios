"""Opt-in PostgreSQL authentication rehearsal; never run against dev or production."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_integration_test_settings
from app.core.credential_verification import VerifiedCredential
from app.core.integration_test_config import require_isolated_test_url, require_owner_test_url
from app.core.sessions import SessionLifecycleService, SessionPolicy, SessionRejected
from app.db.auth_repositories import (
    SqlAlchemyAccountSessionStateRepository,
    SqlAlchemyPasswordCredentialRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserIdentityRepository,
    postgres_lower_ascii_username_predicate,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def auth_runtime_engine():
    settings = get_integration_test_settings()
    try:
        url = require_isolated_test_url(settings.database_url)
    except RuntimeError as exc:
        if settings.database_url is None:
            pytest.skip("INVENTORY_TEST_DATABASE_URL is not configured in .test.env.")
        pytest.fail(str(exc))
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
    with engine.connect() as connection:
        identity = connection.execute(text(
            "SELECT current_database(), session_user, current_user, inet_server_port()"
        )).one()
    if identity != ("inventory_aios_restore_check", "inventory_aios_app", "inventory_aios_app", 5432):
        engine.dispose()
        pytest.fail("Authentication integration target identity was rejected.")
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def auth_owner_engine():
    settings = get_integration_test_settings()
    try:
        url = require_owner_test_url(settings.owner_database_url)
    except RuntimeError as exc:
        if settings.owner_database_url is None:
            pytest.skip("INVENTORY_TEST_OWNER_DATABASE_URL is not configured in .test.env.")
        pytest.fail(str(exc))
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
            database, session_user, current_user, port, revision = connection.execute(text(
                "SELECT current_database(), session_user, current_user, inet_server_port(), "
                "(SELECT version_num FROM public.alembic_version)"
            )).one()
            if (database, session_user, current_user, port, revision) != (
                "inventory_aios_restore_check", "inventory_aios_migrator",
                "inventory_aios_owner", 5432, "d2a8f4c1b790",
            ):
                engine.dispose()
                pytest.fail("Authentication integration target, identity, or migration revision was rejected.")
    yield engine
    engine.dispose()


@pytest.fixture
def auth_user(auth_owner_engine) -> Generator[tuple[uuid.UUID, str], None, None]:
    user_id = uuid.uuid4()
    suffix = uuid.uuid4().hex
    username = f"test_auth_{suffix}"
    with auth_owner_engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
        connection.execute(text(
            "INSERT INTO public.users (id, username, email, display_name, status) "
            "VALUES (:id, :username, :email, :display_name, 'active')"
        ), {"id": user_id, "username": username, "email": f"{suffix}@example.invalid", "display_name": "TEST Auth"})
        connection.execute(text(
            "INSERT INTO public.user_password_credentials "
            "(user_id, password_hash, credential_version) VALUES (:id, :hash, 1)"
        ), {"id": user_id, "hash": "fictional-integration-hash-not-used-for-login"})
    try:
        yield user_id, username
    finally:
        with auth_owner_engine.begin() as connection:
            connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
            connection.execute(text("DELETE FROM public.auth_sessions WHERE user_id=:id"), {"id": user_id})
            connection.execute(text("DELETE FROM public.user_password_credentials WHERE user_id=:id"), {"id": user_id})
            connection.execute(text("DELETE FROM public.users WHERE id=:id"), {"id": user_id})


def _service(session: Session, now: datetime | None = None) -> SessionLifecycleService:
    return SessionLifecycleService(
        sessions=SqlAlchemySessionRepository(session),
        accounts=SqlAlchemyAccountSessionStateRepository(session),
        policy=SessionPolicy(
            absolute_lifetime=timedelta(hours=1),
            inactivity_timeout=timedelta(minutes=30),
            activity_update_interval=timedelta(0),
            maximum_absolute_lifetime=timedelta(hours=2),
        ),
        clock=(lambda: now) if now is not None else lambda: datetime.now(UTC),
    )


def test_real_credential_lookup_session_persistence_revocation_and_version_invalidation(
    auth_runtime_engine, auth_owner_engine, auth_user
) -> None:
    user_id, username = auth_user
    now = datetime.now(UTC)
    with Session(auth_runtime_engine, expire_on_commit=False) as session:
        identities = SqlAlchemyUserIdentityRepository(
            session, username_predicate=postgres_lower_ascii_username_predicate
        ).find_by_canonical_username(username)
        credential = SqlAlchemyPasswordCredentialRepository(session).get_for_user(user_id)
        assert len(identities) == 1 and identities[0].status == "active"
        assert credential is not None and credential.credential_version == 1
        service = _service(session, now)
        first = service.issue(VerifiedCredential(user_id, 1, False))
        second = service.issue(VerifiedCredential(user_id, 1, False))
        assert service.validate(first.token_for_cookie_delivery()).user_id == user_id
        assert service.validate(second.token_for_cookie_delivery()).user_id == user_id
        service.revoke(first.token_for_cookie_delivery())
        with pytest.raises(SessionRejected):
            service.validate(first.token_for_cookie_delivery())
        assert service.validate(second.token_for_cookie_delivery()).user_id == user_id

    with auth_owner_engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
        connection.execute(text(
            "UPDATE public.user_password_credentials SET credential_version=2 WHERE user_id=:id"
        ), {"id": user_id})
    with Session(auth_runtime_engine, expire_on_commit=False) as session:
        with pytest.raises(SessionRejected):
            _service(session).validate(second.token_for_cookie_delivery())
        replacement = _service(session).issue(VerifiedCredential(user_id, 2, False))

    with auth_owner_engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
        connection.execute(text("UPDATE public.users SET status='inactive' WHERE id=:id"), {"id": user_id})
    with Session(auth_runtime_engine, expire_on_commit=False) as session:
        with pytest.raises(SessionRejected):
            _service(session).validate(replacement.token_for_cookie_delivery())


def test_concurrent_independent_session_issue_and_idempotent_revoke(auth_runtime_engine, auth_user) -> None:
    user_id, _ = auth_user
    verified = VerifiedCredential(user_id, 1, False)

    def issue_one():
        with Session(auth_runtime_engine, expire_on_commit=False) as session:
            return _service(session).issue(verified).token_for_cookie_delivery()

    with ThreadPoolExecutor(max_workers=2) as pool:
        tokens = list(pool.map(lambda _: issue_one(), range(2)))
    assert tokens[0] != tokens[1]

    def revoke_one(token: str):
        with Session(auth_runtime_engine, expire_on_commit=False) as session:
            return _service(session).revoke(token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(revoke_one, tokens[:1] * 2))
    assert {result.value for result in results} == {"revoked", "already_revoked"}


def test_invalid_session_insert_rolls_back_without_persisting(auth_runtime_engine, auth_user) -> None:
    from sqlalchemy.exc import IntegrityError

    from app.core.sessions import NewSessionRecord
    from app.db.auth_repositories import SqlAlchemySessionRepository

    user_id, _ = auth_user
    timestamp = datetime.now(UTC)
    digest = uuid.uuid4().bytes + uuid.uuid4().bytes
    invalid = NewSessionRecord(
        session_id=uuid.uuid4(), user_id=user_id, token_digest=digest,
        credential_version=1, created_at=timestamp, last_seen_at=timestamp,
        expires_at=timestamp,
    )
    with Session(auth_runtime_engine, expire_on_commit=False) as session:
        with pytest.raises(IntegrityError):
            SqlAlchemySessionRepository(session).create_if_current(invalid)
        session.rollback()
        found = SqlAlchemySessionRepository(session).get_by_token_digest(digest)
        assert found is None
