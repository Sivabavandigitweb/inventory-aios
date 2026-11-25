"""Shared idempotency claim metadata; no workflow writes are enabled."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.core import User


class IdempotencyRequest(TimestampMixin, Base):
    __tablename__ = "idempotency_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(User.id, ondelete="RESTRICT"), nullable=False,
    )
    operation_scope: Mapped[str] = mapped_column(String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    response_status: Mapped[int | None] = mapped_column(SmallInteger)
    resource_type: Mapped[str | None] = mapped_column(String(80))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    principal: Mapped[User] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "principal_id", "operation_scope", "idempotency_key",
            name="uq_idempotency_requests_principal_scope_key",
        ),
        CheckConstraint(
            "length(trim(operation_scope)) > 0", name="ck_idempotency_requests_scope_nonempty",
        ),
        CheckConstraint(
            "length(trim(idempotency_key)) > 0", name="ck_idempotency_requests_key_nonempty",
        ),
        CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_idempotency_requests_fingerprint_sha256",
        ),
        CheckConstraint(
            "status IN ('processing', 'succeeded')",
            name="ck_idempotency_requests_status",
        ),
        CheckConstraint(
            "(status = 'processing' AND response_status IS NULL "
            "AND resource_type IS NULL AND resource_id IS NULL AND completed_at IS NULL) "
            "OR (status = 'succeeded' AND response_status IS NOT NULL "
            "AND response_status BETWEEN 200 AND 299 "
            "AND completed_at IS NOT NULL)",
            name="ck_idempotency_requests_completion",
        ),
        CheckConstraint(
            "(resource_type IS NULL) = (resource_id IS NULL) "
            "AND (resource_type IS NULL OR length(trim(resource_type)) > 0)",
            name="ck_idempotency_requests_resource_pair",
        ),
        Index("ix_idempotency_requests_principal_status", "principal_id", "status"),
        {"schema": "public"},
    )
