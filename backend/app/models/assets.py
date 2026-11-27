"""Offline asset catalog and receiving-header models; no operational write workflow."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.core import AssetCategory, Employee, Location, Supplier, User


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
    idempotency_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.idempotency_requests.id", name="fk_inventory_products_idempotency_request", ondelete="RESTRICT"), unique=True,
    )

    category: Mapped[AssetCategory] = relationship()

    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_inventory_products_name_nonempty"),
        CheckConstraint("sku IS NULL OR length(trim(sku)) > 0",
                        name="ck_inventory_products_sku_nonempty"),
        CheckConstraint("jsonb_typeof(specifications) = 'object'",
                        name="ck_inventory_products_specifications_object"),
        Index("ix_inventory_products_category_active", "category_id", "active"),
        Index("uq_inventory_products_sku", "sku", unique=True,
              postgresql_where=text("sku IS NOT NULL")),
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
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(Supplier.id, ondelete="RESTRICT"), nullable=True,
    )
    external_reference: Mapped[str | None] = mapped_column(String(150))
    notes: Mapped[str | None] = mapped_column(Text)
    idempotency_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.idempotency_requests.id", name="fk_receipts_idempotency_request", ondelete="RESTRICT"), unique=True,
    )

    received_by: Mapped[User] = relationship()
    location: Mapped[Location] = relationship()
    supplier: Mapped[Supplier | None] = relationship()
    lines: Mapped[list["ReceiptLine"]] = relationship(back_populates="receipt")

    __table_args__ = (
        CheckConstraint("external_reference IS NULL OR length(trim(external_reference)) > 0",
                        name="ck_receipts_external_reference_nonempty"),
        Index("ix_receipts_received_at", "received_at"),
        Index("ix_receipts_received_by_id", "received_by_id"),
        Index("ix_receipts_location_received_at", "location_id", "received_at"),
        {"schema": "public"},
    )


class ReceiptLine(Base):
    __tablename__ = "receipt_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    receipt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.receipts.id", ondelete="RESTRICT"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(InventoryProduct.id, ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    tracking_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")

    receipt: Mapped[Receipt] = relationship(back_populates="lines")
    product: Mapped[InventoryProduct] = relationship()

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_receipt_lines_quantity_positive"),
        CheckConstraint("length(trim(unit)) > 0", name="ck_receipt_lines_unit_nonempty"),
        CheckConstraint("tracking_mode IN ('individual', 'quantity')", name="ck_receipt_lines_tracking_mode"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'registered')", name="ck_receipt_lines_status"),
        Index("ix_receipt_lines_receipt", "receipt_id"),
        Index("ix_receipt_lines_product", "product_id"),
        {"schema": "public"},
    )


class TrackedAsset(TimestampMixin, Base):
    __tablename__ = "tracked_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(InventoryProduct.id, ondelete="RESTRICT"), nullable=False)
    receipt_line_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.receipt_lines.id", ondelete="RESTRICT"), nullable=True)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(Location.id, ondelete="RESTRICT"), nullable=False)
    asset_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(150), nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(20), nullable=False)
    condition: Mapped[str | None] = mapped_column(String(40), nullable=True)
    idempotency_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.idempotency_requests.id", name="fk_tracked_assets_idempotency_request", ondelete="RESTRICT"), unique=True,
    )

    product: Mapped[InventoryProduct] = relationship()
    location: Mapped[Location] = relationship()
    receipt_line: Mapped[ReceiptLine | None] = relationship()

    __table_args__ = (
        CheckConstraint("lifecycle_status IN ('available', 'allocated', 'repair', 'damaged', 'disposed')",
            name="ck_tracked_assets_lifecycle_status"),
        CheckConstraint("asset_number IS NULL OR length(trim(asset_number)) > 0",
            name="ck_tracked_assets_asset_number_nonempty"),
        Index("uq_tracked_assets_asset_number", "asset_number", unique=True,
            postgresql_where=text("asset_number IS NOT NULL")),
        Index("ix_tracked_assets_product_status", "product_id", "lifecycle_status"),
        Index("ix_tracked_assets_location_status", "location_id", "lifecycle_status"),
        {"schema": "public"},
    )


class QuantityInventoryLot(TimestampMixin, Base):
    __tablename__ = "quantity_inventory_lots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(InventoryProduct.id, ondelete="RESTRICT"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(Location.id, ondelete="RESTRICT"), nullable=False)
    receipt_line_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.receipt_lines.id", ondelete="RESTRICT"), nullable=True)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    idempotency_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("public.idempotency_requests.id", name="fk_quantity_inventory_lots_idempotency_request", ondelete="RESTRICT"), unique=True,
    )

    __table_args__ = (
        CheckConstraint("length(trim(unit)) > 0", name="ck_quantity_inventory_lots_unit_nonempty"),
        CheckConstraint("quantity >= 0", name="ck_quantity_inventory_lots_quantity_nonnegative"),
        Index("ix_quantity_inventory_lots_product_location_unit", "product_id", "location_id", "unit"),
        {"schema": "public"},
    )


class InventoryBalance(Base):
    __tablename__ = "inventory_balances"

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(InventoryProduct.id, ondelete="RESTRICT"), primary_key=True)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(Location.id, ondelete="RESTRICT"), primary_key=True)
    unit: Mapped[str] = mapped_column(String(30), primary_key=True)
    on_hand: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, server_default="0")
    reserved: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, server_default="0")
    quarantined: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False,
        server_default=text("now()"), onupdate=text("now()"))

    __table_args__ = (
        CheckConstraint("length(trim(unit)) > 0", name="ck_inventory_balances_unit_nonempty"),
        CheckConstraint("on_hand >= 0", name="ck_inventory_balances_on_hand_nonnegative"),
        CheckConstraint("reserved >= 0 AND quarantined >= 0 AND reserved + quarantined <= on_hand",
            name="ck_inventory_balances_reserved_valid"),
        Index("ix_inventory_balances_location_product", "location_id", "product_id"),
        {"schema": "public"},
    )


class InventoryMovement(Base):
    __tablename__ = "inventory_movements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(InventoryProduct.id, ondelete="RESTRICT"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(Location.id, ondelete="RESTRICT"), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity_delta: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    on_hand_delta: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, server_default="0")
    reserved_delta: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, server_default="0")
    quarantined_delta: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, server_default="0")
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"), nullable=True)
    idempotency_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.idempotency_requests.id", name="fk_inventory_movements_idem_request",
                   ondelete="RESTRICT"), nullable=False, unique=True)
    reference_type: Mapped[str | None] = mapped_column(String(60))
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    __table_args__ = (
        CheckConstraint("quantity_delta <> 0 OR on_hand_delta <> 0 OR reserved_delta <> 0 OR quarantined_delta <> 0",
            name="ck_inventory_movements_nonzero_delta"),
        CheckConstraint("length(trim(unit)) > 0", name="ck_inventory_movements_unit_nonempty"),
        CheckConstraint("movement_type IN ('receipt', 'adjustment', 'allocation', 'return', 'disposal', 'quarantine', 'quarantine_release', 'quarantine_disposal')",
            name="ck_inventory_movements_type"),
        CheckConstraint("(reference_type IS NULL) = (reference_id IS NULL)",
            name="ck_inventory_movements_reference_pair"),
        Index("ix_inventory_movements_product_location_time", "product_id", "location_id", "occurred_at"),
        {"schema": "public"},
    )


class AssetRegistrationEvent(Base):
    __tablename__ = "asset_registration_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    tracked_asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(TrackedAsset.id, ondelete="RESTRICT"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict,
        server_default=text("'{}'::jsonb"))

    __table_args__ = (
        CheckConstraint("event_type IN ('pending', 'approved', 'registered', 'rejected')",
            name="ck_asset_registration_events_type"),
        CheckConstraint("jsonb_typeof(details) = 'object'", name="ck_asset_registration_events_details_object"),
        Index("ix_asset_registration_events_asset_time", "tracked_asset_id", "occurred_at"),
        {"schema": "public"},
    )


class EmployeeSourceIdentity(Base):
    """Mapping from a configured source identity to a stable local employee ID."""

    __tablename__ = "employee_source_identities"

    source_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(Employee.id, ondelete="RESTRICT"), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    __table_args__ = (
        CheckConstraint("length(trim(source_key)) > 0", name="ck_employee_source_identities_source_nonempty"),
        CheckConstraint("length(trim(external_id)) > 0", name="ck_employee_source_identities_external_nonempty"),
        {"schema": "public"},
    )


class EmployeeSyncRun(Base):
    __tablename__ = "employee_sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    source_key: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    read_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed', 'dry_run')", name="ck_employee_sync_runs_status"),
        CheckConstraint("read_count >= 0 AND inserted_count >= 0 AND updated_count >= 0 AND unchanged_count >= 0 AND conflict_count >= 0",
            name="ck_employee_sync_runs_counts_nonnegative"),
        Index("ix_employee_sync_runs_source_started", "source_key", "started_at"),
        {"schema": "public"},
    )
