"""Persistence contracts for inventory transactions; services remain policy gated."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.core import Employee, Location, User


class Allocation(TimestampMixin, Base):
    __tablename__ = "allocations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(Employee.id, ondelete="RESTRICT"), nullable=False)
    requested_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    idempotency_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.idempotency_requests.id", ondelete="RESTRICT"), nullable=False, unique=True)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'issued', 'cancelled', 'partially_returned', 'returned')",
                        name="ck_allocations_status"),
        Index("ix_allocations_employee_status", "employee_id", "status"),
        {"schema": "public"},
    )


class AllocationLine(Base):
    __tablename__ = "allocation_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    allocation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.allocations.id", ondelete="RESTRICT"), nullable=False)
    tracked_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.tracked_assets.id", ondelete="RESTRICT"))
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.inventory_products.id", ondelete="RESTRICT"))
    location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey(Location.id, ondelete="RESTRICT"))
    unit: Mapped[str | None] = mapped_column(String(30))
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    returned_quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")

    __table_args__ = (
        CheckConstraint("quantity > 0 AND returned_quantity >= 0 AND returned_quantity <= quantity",
                        name="ck_allocation_lines_quantity_valid"),
        CheckConstraint("(tracked_asset_id IS NOT NULL AND product_id IS NULL AND location_id IS NULL AND unit IS NULL AND quantity = 1) OR "
                        "(tracked_asset_id IS NULL AND product_id IS NOT NULL AND location_id IS NOT NULL AND unit IS NOT NULL)",
                        name="ck_allocation_lines_tracking_target"),
        Index("ix_allocation_lines_allocation", "allocation_id"),
        CheckConstraint("status IN ('pending', 'active', 'partially_returned', 'returned', 'cancelled')",
                        name="ck_allocation_lines_status"),
        Index("uq_allocation_lines_active_asset", "tracked_asset_id", unique=True,
              postgresql_where=text("tracked_asset_id IS NOT NULL AND status IN ('pending', 'active', 'partially_returned')")),
        {"schema": "public"},
    )


class InventoryReturn(TimestampMixin, Base):
    __tablename__ = "inventory_returns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    allocation_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.allocation_lines.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    condition: Mapped[str] = mapped_column(String(20), nullable=False)
    resolved_quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    recorded_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"), nullable=False)
    idempotency_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.idempotency_requests.id", ondelete="RESTRICT"), nullable=False, unique=True)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_inventory_returns_quantity_positive"),
        CheckConstraint("resolved_quantity >= 0 AND resolved_quantity <= quantity",
                        name="ck_inventory_returns_resolved_quantity"),
        CheckConstraint("condition IN ('good', 'repair', 'damaged', 'unknown')", name="ck_inventory_returns_condition"),
        CheckConstraint("status IN ('pending', 'verified', 'rejected')", name="ck_inventory_returns_status"),
        Index("ix_inventory_returns_line_status", "allocation_line_id", "status"),
        {"schema": "public"},
    )


class AssetRepair(TimestampMixin, Base):
    __tablename__ = "asset_repairs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    tracked_asset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.tracked_assets.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="reported")
    reported_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    internal_reference: Mapped[str | None] = mapped_column(String(120))
    issue_details: Mapped[str | None] = mapped_column(Text)
    repair_provider: Mapped[str | None] = mapped_column(String(200))
    cost_amount: Mapped[float | None] = mapped_column(Numeric(14, 2))
    cost_currency: Mapped[str | None] = mapped_column(String(3))
    completion_condition: Mapped[str | None] = mapped_column(String(20))
    completion_notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("status IN ('reported', 'in_progress', 'completed', 'cancelled')", name="ck_asset_repairs_status"),
        CheckConstraint("(status = 'completed') = (closed_at IS NOT NULL)", name="ck_asset_repairs_closed_at"),
        CheckConstraint("issue_details IS NULL OR length(trim(issue_details)) > 0", name="ck_asset_repairs_issue_details_nonempty"),
        CheckConstraint("cost_amount IS NULL OR cost_amount >= 0", name="ck_asset_repairs_cost_nonnegative"),
        CheckConstraint("(cost_amount IS NULL) = (cost_currency IS NULL)", name="ck_asset_repairs_cost_currency_pair"),
        CheckConstraint("cost_currency IS NULL OR cost_currency ~ '^[A-Z]{3}$'", name="ck_asset_repairs_cost_currency_code"),
        CheckConstraint("completion_condition IS NULL OR completion_condition IN ('good', 'damaged')",
                        name="ck_asset_repairs_completion_condition"),
        CheckConstraint("completion_condition IS NULL OR status = 'completed'",
                        name="ck_asset_repairs_completion_condition_required"),
        Index("ix_asset_repairs_asset_status", "tracked_asset_id", "status"),
        Index("uq_asset_repairs_one_open", "tracked_asset_id", unique=True,
              postgresql_where=text("status IN ('reported', 'in_progress')")),
        {"schema": "public"},
    )


class DisposalRequest(TimestampMixin, Base):
    __tablename__ = "disposal_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    tracked_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.tracked_assets.id", ondelete="RESTRICT"))
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.inventory_products.id", ondelete="RESTRICT"))
    location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey(Location.id, ondelete="RESTRICT"))
    unit: Mapped[str | None] = mapped_column(String(30))
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    requested_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"), nullable=False)
    idempotency_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.idempotency_requests.id", ondelete="RESTRICT"), nullable=False, unique=True)
    reason_code: Mapped[str | None] = mapped_column(String(40))
    condition: Mapped[str | None] = mapped_column(String(20))
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_disposal_requests_quantity_positive"),
        CheckConstraint("(tracked_asset_id IS NOT NULL AND product_id IS NULL AND location_id IS NULL AND unit IS NULL AND quantity = 1) OR "
                        "(tracked_asset_id IS NULL AND product_id IS NOT NULL AND location_id IS NOT NULL AND unit IS NOT NULL)",
                        name="ck_disposal_requests_target"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'completed', 'cancelled')", name="ck_disposal_requests_status"),
        CheckConstraint("reason_code IS NULL OR length(trim(reason_code)) > 0", name="ck_disposal_requests_reason_nonempty"),
        CheckConstraint("condition IS NULL OR condition IN ('good', 'repair', 'damaged', 'unknown')",
                        name="ck_disposal_requests_condition"),
        CheckConstraint("(completed_at IS NULL) = (completed_by_id IS NULL)",
                        name="ck_disposal_requests_completion"),
        Index("uq_disposal_requests_open_asset", "tracked_asset_id", unique=True,
              postgresql_where=text("tracked_asset_id IS NOT NULL AND status IN ('pending', 'approved')")),
        {"schema": "public"},
    )


class EmployeeExitClearance(TimestampMixin, Base):
    __tablename__ = "employee_exit_clearances"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    employee_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(Employee.id, ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    opened_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"), nullable=False)
    completed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="unverified")

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'in_progress', 'completed', 'cancelled')", name="ck_exit_clearance_status"),
        CheckConstraint("verification_status IN ('unverified', 'verified', 'exceptions')", name="ck_exit_clearance_verification"),
        CheckConstraint("(status = 'completed') = (completed_at IS NOT NULL AND completed_by_id IS NOT NULL)",
                        name="ck_exit_clearance_completion"),
        Index("ix_exit_clearance_status", "status"),
        Index("uq_exit_clearance_open_employee", "employee_id", unique=True,
              postgresql_where=text("status IN ('pending', 'in_progress')")),
        {"schema": "public"},
    )


class WorkflowApproval(TimestampMixin, Base):
    __tablename__ = "workflow_approvals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    required_capability: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    requested_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"), nullable=False)
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason_code: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        CheckConstraint("entity_type IN ('product', 'receiving', 'asset_registration', 'quantity_registration', 'allocation', 'return', 'disposal', 'repair', 'exit_clearance', 'quantity_disposition')", name="ck_workflow_approvals_entity_type"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="ck_workflow_approvals_status"),
        CheckConstraint("length(trim(required_capability)) > 0", name="ck_workflow_approvals_capability_nonempty"),
        CheckConstraint("decided_by_id IS NULL OR requested_by_id <> decided_by_id",
                        name="ck_workflow_approvals_no_self_approval"),
        CheckConstraint("(status IN ('approved', 'rejected')) = (decided_at IS NOT NULL AND decided_by_id IS NOT NULL)",
                        name="ck_workflow_approvals_decision"),
        CheckConstraint("decision_reason_code IS NULL OR length(trim(decision_reason_code)) > 0",
                        name="ck_workflow_approvals_reason_nonempty"),
        Index("ix_workflow_approvals_status_created", "status", "created_at"),
        Index("ix_workflow_approvals_entity", "entity_type", "entity_id"),
        Index("uq_workflow_approvals_pending_capability", "entity_type", "entity_id", "required_capability",
              unique=True, postgresql_where=text("status = 'pending'")),
        {"schema": "public"},
    )


class AssetRegistrationRequest(TimestampMixin, Base):
    __tablename__ = "asset_registration_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    receipt_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.receipt_lines.id", ondelete="RESTRICT"), nullable=False)
    asset_number: Mapped[str | None] = mapped_column(String(100))
    serial_number: Mapped[str | None] = mapped_column(String(150))
    condition: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    submitted_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"), nullable=False)
    idempotency_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.idempotency_requests.id", ondelete="RESTRICT"), nullable=False, unique=True)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'registered', 'cancelled')", name="ck_asset_registration_requests_status"),
        CheckConstraint("asset_number IS NULL OR length(trim(asset_number)) > 0", name="ck_asset_registration_requests_asset_number"),
        Index("ix_asset_registration_requests_receipt_line_status", "receipt_line_id", "status"),
        {"schema": "public"},
    )


class QuantityRegistrationRequest(TimestampMixin, Base):
    __tablename__ = "quantity_registration_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    receipt_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.receipt_lines.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    submitted_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"), nullable=False)
    idempotency_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.idempotency_requests.id", ondelete="RESTRICT"), nullable=False, unique=True)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_quantity_registration_requests_quantity_positive"),
        CheckConstraint("length(trim(unit)) > 0", name="ck_quantity_registration_requests_unit_nonempty"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'registered', 'cancelled')", name="ck_quantity_registration_requests_status"),
        Index("ix_quantity_registration_requests_receipt_line_status", "receipt_line_id", "status"),
        {"schema": "public"},
    )


class QuantityDispositionRequest(TimestampMixin, Base):
    __tablename__ = "quantity_disposition_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    inventory_return_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.inventory_returns.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    disposition: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    requested_by_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"), nullable=False)
    idempotency_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True),
        ForeignKey("public.idempotency_requests.id", ondelete="RESTRICT"), nullable=False, unique=True)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_quantity_disposition_quantity_positive"),
        CheckConstraint("disposition IN ('release', 'dispose')", name="ck_quantity_disposition_kind"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'completed')",
                        name="ck_quantity_disposition_status"),
        Index("ix_quantity_disposition_return_status", "inventory_return_id", "status"),
        {"schema": "public"},
    )


class InventoryNotification(Base):
    __tablename__ = "inventory_notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=text("gen_random_uuid()"))
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True),
        ForeignKey(User.id, ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending_policy")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("event_type IN ('registration_pending', 'approval_pending', 'return_outstanding', 'repair_updated', 'information_missing', 'warranty_reminder')",
                        name="ck_inventory_notifications_event_type"),
        CheckConstraint("entity_type IN ('receipt', 'allocation', 'inventory_return', 'asset_repair', 'employee_exit_clearance', 'disposal_request')",
                        name="ck_inventory_notifications_entity_type"),
        CheckConstraint("status IN ('pending_policy', 'ready', 'read', 'suppressed')", name="ck_inventory_notifications_status"),
        Index("ix_inventory_notifications_recipient_status", "recipient_user_id", "status", "created_at"),
        {"schema": "public"},
    )
