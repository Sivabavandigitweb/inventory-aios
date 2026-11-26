"""Credential and session persistence structures; no auth flow is enabled here."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.core import User


class UserPasswordCredential(TimestampMixin, Base):
    """One optional local password hash for a stable Inventory AIOS user."""

    __tablename__ = "user_password_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"),
        primary_key=True,
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    credential_version: Mapped[int] = mapped_column(
        nullable=False, default=1, server_default=text("1")
    )

    user: Mapped[User] = relationship()

    __table_args__ = (
        CheckConstraint(
            "credential_version > 0",
            name="ck_user_password_credentials_version_positive",
        ),
        {"schema": "public"},
    )

    def __repr__(self) -> str:
        return f"<UserPasswordCredential user_id={self.user_id!r}>"


class AuthSession(Base):
    """Hashed opaque-session lookup data; raw browser tokens are never stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(User.id, ondelete="RESTRICT"), nullable=False
    )
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    credential_version: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        CheckConstraint(
            "octet_length(token_hash) = 32",
            name="ck_auth_sessions_token_hash_length",
        ),
        CheckConstraint(
            "credential_version > 0",
            name="ck_auth_sessions_credential_version_positive",
        ),
        CheckConstraint(
            "last_seen_at >= created_at",
            name="ck_auth_sessions_last_seen_after_creation",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_auth_sessions_expiry_after_creation",
        ),
        Index("ix_auth_sessions_user_revoked", "user_id", "revoked_at"),
        Index("ix_auth_sessions_expires_at", "expires_at"),
        {"schema": "public"},
    )

    def __repr__(self) -> str:
        return f"<AuthSession id={self.id!r} user_id={self.user_id!r}>"
