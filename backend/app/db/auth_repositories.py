"""SQLAlchemy adapters for the offline authentication service ports.

These adapters are not wired into the operational application. Reads do not commit.
The session repository commits only its own mutations and requires a clean,
request-scoped SQLAlchemy Session. No adapter creates a connection by itself.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import exists, func, insert, literal, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.core.credential_verification import LoginUser, PasswordCredentialRecord
from app.core.sessions import (
    ActivityUpdateResult,
    CurrentAccountSessionState,
    NewSessionRecord,
    SessionCreationStateChanged,
    SessionRevocationResult,
    SessionTokenDigestCollision,
    StoredSessionRecord,
)
from app.models import User
from app.models.authentication import AuthSession, UserPasswordCredential


def postgres_lower_ascii_username_predicate(canonical_username: str) -> ColumnElement[bool]:
    """Use the existing expression-index-compatible lookup for lowercase ASCII."""
    if (
        not isinstance(canonical_username, str)
        or not canonical_username
        or not canonical_username.isascii()
        or canonical_username != canonical_username.lower()
    ):
        raise ValueError("A canonical lowercase ASCII username is required.")
    return func.lower(User.username) == canonical_username


class SqlAlchemyUserIdentityRepository:
    """User lookup with an explicitly injected SQL predicate.

    Username normalization remains unresolved. The caller must supply a predicate
    compatible with the selected normalization and existing PostgreSQL index.
    Results are capped at two so ambiguous identities fail closed upstream.
    """

    def __init__(
        self,
        session: Session,
        *,
        username_predicate: Callable[[str], ColumnElement[bool]],
    ) -> None:
        self._session = session
        self._username_predicate = username_predicate

    def find_by_canonical_username(self, canonical_username: str) -> list[LoginUser]:
        statement = (
            select(User.id, User.username, User.status)
            .where(self._username_predicate(canonical_username))
            .limit(2)
        )
        rows = self._session.execute(statement).all()
        return [LoginUser(user_id=row.id, username=row.username, status=row.status) for row in rows]


class SqlAlchemyPasswordCredentialRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_for_user(self, user_id: UUID) -> PasswordCredentialRecord | None:
        row = self._session.execute(
            select(
                UserPasswordCredential.user_id,
                UserPasswordCredential.password_hash,
                UserPasswordCredential.credential_version,
            ).where(UserPasswordCredential.user_id == user_id)
        ).one_or_none()
        if row is None:
            return None
        return PasswordCredentialRecord(
            user_id=row.user_id,
            password_hash=row.password_hash,
            credential_version=row.credential_version,
        )


class SqlAlchemyAccountSessionStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_current_state(self, user_id: UUID) -> CurrentAccountSessionState | None:
        row = self._session.execute(
            select(User.id, User.status, UserPasswordCredential.credential_version)
            .outerjoin(UserPasswordCredential, UserPasswordCredential.user_id == User.id)
            .where(User.id == user_id)
        ).one_or_none()
        if row is None:
            return None
        return CurrentAccountSessionState(row.id, row.status, row.credential_version)


class SqlAlchemySessionRepository:
    """Conditional PostgreSQL persistence adapter with explicit mutation commits."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_if_current(self, record: NewSessionRecord) -> None:
        self._require_clean_session()
        if len(record.token_digest) != 32 or type(record.credential_version) is not int:
            raise ValueError("Invalid authentication session record.")
        columns = [
            AuthSession.id,
            AuthSession.user_id,
            AuthSession.token_hash,
            AuthSession.credential_version,
            AuthSession.created_at,
            AuthSession.last_seen_at,
            AuthSession.expires_at,
        ]
        source = (
            select(
                literal(record.session_id),
                literal(record.user_id),
                literal(record.token_digest),
                literal(record.credential_version),
                literal(record.created_at),
                literal(record.last_seen_at),
                literal(record.expires_at),
            )
            .select_from(User)
            .join(UserPasswordCredential, UserPasswordCredential.user_id == User.id)
            .where(
                User.id == record.user_id,
                User.status == "active",
                UserPasswordCredential.credential_version == record.credential_version,
            )
        )
        statement = insert(AuthSession).from_select(columns, source).returning(AuthSession.id)
        try:
            with self._session.begin_nested():
                inserted_id = self._session.execute(statement).scalar_one_or_none()
                if inserted_id is None:
                    raise SessionCreationStateChanged
            self._session.commit()
        except IntegrityError as error:
            if _constraint_name(error) == "uq_auth_sessions_token_hash":
                raise SessionTokenDigestCollision from None
            self._rollback_safely()
            raise
        except SessionCreationStateChanged:
            raise
        except Exception:
            self._rollback_safely()
            raise

    def get_by_token_digest(self, token_digest: bytes) -> StoredSessionRecord | None:
        row = self._session.execute(
            select(
                AuthSession.id,
                AuthSession.user_id,
                AuthSession.token_hash,
                AuthSession.credential_version,
                AuthSession.created_at,
                AuthSession.last_seen_at,
                AuthSession.expires_at,
                AuthSession.revoked_at,
            ).where(AuthSession.token_hash == token_digest)
        ).one_or_none()
        if row is None:
            return None
        return StoredSessionRecord(
            session_id=row.id,
            user_id=row.user_id,
            token_digest=row.token_hash,
            credential_version=row.credential_version,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
        )

    def update_activity_if_current(
        self,
        *,
        session_id: UUID,
        expected_user_id: UUID,
        expected_credential_version: int,
        expected_last_seen_at: datetime,
        checked_at: datetime,
        new_last_seen_at: datetime,
        inactivity_timeout: timedelta,
    ) -> ActivityUpdateResult:
        self._require_clean_session()
        account_is_current = _active_credential_exists(
            user_column=AuthSession.user_id,
            credential_version=expected_credential_version,
        )
        statement = (
            update(AuthSession)
            .where(
                AuthSession.id == session_id,
                AuthSession.user_id == expected_user_id,
                AuthSession.credential_version == expected_credential_version,
                AuthSession.last_seen_at == expected_last_seen_at,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > checked_at,
                AuthSession.last_seen_at > checked_at - inactivity_timeout,
                new_last_seen_at >= AuthSession.last_seen_at,
                new_last_seen_at < AuthSession.expires_at,
                account_is_current,
            )
            .values(last_seen_at=new_last_seen_at)
            .returning(AuthSession.id)
        )
        if self._session.execute(statement).scalar_one_or_none() is not None:
            self._session.commit()
            return ActivityUpdateResult.UPDATED

        current = self._session.execute(
            select(
                AuthSession.user_id,
                AuthSession.credential_version,
                AuthSession.last_seen_at,
                AuthSession.expires_at,
                AuthSession.revoked_at,
            ).where(AuthSession.id == session_id)
        ).one_or_none()
        if (
            current is not None
            and current.user_id == expected_user_id
            and current.credential_version == expected_credential_version
            and current.revoked_at is None
            and current.last_seen_at > expected_last_seen_at
            and current.last_seen_at > checked_at - inactivity_timeout
            and current.expires_at > checked_at
        ):
            return ActivityUpdateResult.ALREADY_ADVANCED
        return ActivityUpdateResult.SESSION_INVALID

    def revoke_one_if_active(
        self, session_id: UUID, revoked_at: datetime
    ) -> SessionRevocationResult:
        self._require_clean_session()
        statement = (
            update(AuthSession)
            .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
            .returning(AuthSession.id)
        )
        if self._session.execute(statement).scalar_one_or_none() is not None:
            self._session.commit()
            return SessionRevocationResult.REVOKED
        existing = self._session.execute(
            select(AuthSession.revoked_at).where(AuthSession.id == session_id)
        ).one_or_none()
        if existing is None:
            return SessionRevocationResult.NOT_FOUND
        if existing.revoked_at is not None:
            return SessionRevocationResult.ALREADY_REVOKED
        raise RuntimeError("Session revocation state changed unexpectedly.")

    def revoke_all_for_user(self, user_id: UUID, revoked_at: datetime) -> int:
        self._require_clean_session()
        statement = (
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
            .returning(AuthSession.id)
        )
        count = len(self._session.execute(statement).all())
        if count:
            self._session.commit()
        return count

    def _require_clean_session(self) -> None:
        if self._session.new or self._session.dirty or self._session.deleted:
            raise RuntimeError("Authentication repository requires a clean request session.")

    def _rollback_safely(self) -> None:
        try:
            self._session.rollback()
        except Exception:
            pass


def _active_credential_exists(*, user_column: Any, credential_version: int):
    return exists(
        select(literal(1))
        .select_from(User)
        .join(UserPasswordCredential, UserPasswordCredential.user_id == User.id)
        .where(
            User.id == user_column,
            User.status == "active",
            UserPasswordCredential.credential_version == credential_version,
        )
    )


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostic = getattr(error.orig, "diag", None)
    name = getattr(diagnostic, "constraint_name", None)
    return name if isinstance(name, str) else None
