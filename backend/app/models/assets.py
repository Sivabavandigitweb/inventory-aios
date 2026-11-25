"""Offline asset catalog and receiving-header models; no operational write workflow."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.core import AssetCategory, Location, User


class InventoryProduct(TimestampMixin, Base):
    """Shared catalog identity, independent of stock units and procurement policy."""

    __tablename__ = "inventory_products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(AssetCategory.id, ondelete="RESTRICT"), nullable=False,
    )
    sku: Mapped[str | None] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(150))
    model: Mapped[str | None] = mapped_column(String(150))
    specifications: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"),
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"),
    )

    category: Mapped[AssetCategory] = relationship()

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_inventory_products_name_nonempty"),
        CheckConstraint("sku IS NULL OR length(trim(sku)) > 0",
                        name="ck_inventory_products_sku_nonempty"),
        CheckConstraint("jsonb_typeof(specifications) = 'object'",
                        name="ck_inventory_products_specifications_object"),
        Index("ix_inventory_products_category_active", "category_id", "active"),
        {"schema": "public"},
    )


class Receipt(TimestampMixin, Base):
    """Arrival header only; this model does not authorize receipt finalization."""

    __tablename__ = "receipts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(User.id, ondelete="RESTRICT"), nullable=False,
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(Location.id, ondelete="RESTRICT"), nullable=False,
    )
    external_reference: Mapped[str | None] = mapped_column(String(150))
    notes: Mapped[str | None] = mapped_column(Text)

    received_by: Mapped[User] = relationship()
    location: Mapped[Location] = relationship()

    __table_args__ = (
        CheckConstraint("external_reference IS NULL OR length(trim(external_reference)) > 0",
                        name="ck_receipts_external_reference_nonempty"),
        Index("ix_receipts_received_at", "received_at"),
        Index("ix_receipts_received_by_id", "received_by_id"),
        Index("ix_receipts_location_received_at", "location_id", "received_at"),
        {"schema": "public"},
    )
