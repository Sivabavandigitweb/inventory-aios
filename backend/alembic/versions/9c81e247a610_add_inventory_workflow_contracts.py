"""Add inventory transaction, approval, notification and audit value contracts.

Revision ID: 9c81e247a610
Revises: 4b6f10a2c903
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "9c81e247a610"
down_revision: Union[str, None] = "4b6f10a2c903"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _id() -> sa.Column:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def upgrade() -> None:
    op.execute("ALTER TABLE public.audit_events ADD COLUMN previous_values JSONB")
    op.execute("ALTER TABLE public.audit_events ADD COLUMN updated_values JSONB")
    op.create_check_constraint("ck_audit_events_previous_values_object", "audit_events",
        "previous_values IS NULL OR jsonb_typeof(previous_values) = 'object'", schema="public")
    op.create_check_constraint("ck_audit_events_updated_values_object", "audit_events",
        "updated_values IS NULL OR jsonb_typeof(updated_values) = 'object'", schema="public")

    op.create_table("allocations", _id(),
        sa.Column("employee_id", sa.UUID(), nullable=False),
        sa.Column("requested_by_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("idempotency_request_id", sa.UUID(), nullable=False), *_timestamps(),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'issued', 'cancelled', 'partially_returned', 'returned')", name="ck_allocations_status"),
        sa.ForeignKeyConstraint(["employee_id"], ["public.employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["idempotency_request_id"], ["public.idempotency_requests.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_allocations"),
        sa.UniqueConstraint("idempotency_request_id", name="uq_allocations_idempotency_request_id"), schema="public")
    op.create_index("ix_allocations_employee_status", "allocations", ["employee_id", "status"], schema="public")

    op.create_table("allocation_lines", _id(),
        sa.Column("allocation_id", sa.UUID(), nullable=False),
        sa.Column("tracked_asset_id", sa.UUID()), sa.Column("product_id", sa.UUID()),
        sa.Column("location_id", sa.UUID()), sa.Column("unit", sa.String(30)),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("returned_quantity", sa.Numeric(14, 3), server_default="0", nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.CheckConstraint("quantity > 0 AND returned_quantity >= 0 AND returned_quantity <= quantity", name="ck_allocation_lines_quantity_valid"),
        sa.CheckConstraint("(tracked_asset_id IS NOT NULL AND product_id IS NULL AND location_id IS NULL AND unit IS NULL AND quantity = 1) OR (tracked_asset_id IS NULL AND product_id IS NOT NULL AND location_id IS NOT NULL AND unit IS NOT NULL)", name="ck_allocation_lines_tracking_target"),
        sa.CheckConstraint("status IN ('pending', 'active', 'partially_returned', 'returned', 'cancelled')", name="ck_allocation_lines_status"),
        sa.ForeignKeyConstraint(["allocation_id"], ["public.allocations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tracked_asset_id"], ["public.tracked_assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["public.inventory_products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["public.locations.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_allocation_lines"), schema="public")
    op.create_index("ix_allocation_lines_allocation", "allocation_lines", ["allocation_id"], schema="public")
    op.create_index("uq_allocation_lines_active_asset", "allocation_lines", ["tracked_asset_id"], unique=True,
        postgresql_where=sa.text("tracked_asset_id IS NOT NULL AND status IN ('pending', 'active', 'partially_returned')"), schema="public")

    op.create_table("inventory_returns", _id(),
        sa.Column("allocation_line_id", sa.UUID(), nullable=False), sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("condition", sa.String(20), nullable=False), sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("recorded_by_id", sa.UUID(), nullable=False), sa.Column("idempotency_request_id", sa.UUID(), nullable=False), *_timestamps(),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_returns_quantity_positive"),
        sa.CheckConstraint("condition IN ('good', 'repair', 'damaged', 'unknown')", name="ck_inventory_returns_condition"),
        sa.CheckConstraint("status IN ('pending', 'verified', 'rejected')", name="ck_inventory_returns_status"),
        sa.ForeignKeyConstraint(["allocation_line_id"], ["public.allocation_lines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["idempotency_request_id"], ["public.idempotency_requests.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_returns"),
        sa.UniqueConstraint("idempotency_request_id", name="uq_inventory_returns_idempotency_request_id"), schema="public")
    op.create_index("ix_inventory_returns_line_status", "inventory_returns", ["allocation_line_id", "status"], schema="public")

    op.create_table("asset_repairs", _id(),
        sa.Column("tracked_asset_id", sa.UUID(), nullable=False), sa.Column("status", sa.String(20), server_default="reported", nullable=False),
        sa.Column("reported_by_id", sa.UUID(), nullable=False), sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)), sa.Column("internal_reference", sa.String(120)), *_timestamps(),
        sa.CheckConstraint("status IN ('reported', 'in_progress', 'completed', 'cancelled')", name="ck_asset_repairs_status"),
        sa.CheckConstraint("(status = 'completed') = (closed_at IS NOT NULL)", name="ck_asset_repairs_closed_at"),
        sa.ForeignKeyConstraint(["tracked_asset_id"], ["public.tracked_assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reported_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_asset_repairs"), schema="public")
    op.create_index("ix_asset_repairs_asset_status", "asset_repairs", ["tracked_asset_id", "status"], schema="public")
    op.create_index("uq_asset_repairs_one_open", "asset_repairs", ["tracked_asset_id"], unique=True,
        postgresql_where=sa.text("status IN ('reported', 'in_progress')"), schema="public")

    op.create_table("disposal_requests", _id(),
        sa.Column("tracked_asset_id", sa.UUID()), sa.Column("product_id", sa.UUID()), sa.Column("location_id", sa.UUID()),
        sa.Column("unit", sa.String(30)), sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("requested_by_id", sa.UUID(), nullable=False), sa.Column("idempotency_request_id", sa.UUID(), nullable=False), *_timestamps(),
        sa.CheckConstraint("quantity > 0", name="ck_disposal_requests_quantity_positive"),
        sa.CheckConstraint("(tracked_asset_id IS NOT NULL AND product_id IS NULL AND location_id IS NULL AND unit IS NULL AND quantity = 1) OR (tracked_asset_id IS NULL AND product_id IS NOT NULL AND location_id IS NOT NULL AND unit IS NOT NULL)", name="ck_disposal_requests_target"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'completed', 'cancelled')", name="ck_disposal_requests_status"),
        sa.ForeignKeyConstraint(["tracked_asset_id"], ["public.tracked_assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["public.inventory_products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["public.locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["idempotency_request_id"], ["public.idempotency_requests.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_disposal_requests"),
        sa.UniqueConstraint("idempotency_request_id", name="uq_disposal_requests_idempotency_request_id"), schema="public")
    op.create_index("uq_disposal_requests_open_asset", "disposal_requests", ["tracked_asset_id"], unique=True,
        postgresql_where=sa.text("tracked_asset_id IS NOT NULL AND status IN ('pending', 'approved')"), schema="public")

    op.create_table("employee_exit_clearances", _id(),
        sa.Column("employee_id", sa.UUID(), nullable=False), sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("opened_by_id", sa.UUID(), nullable=False), sa.Column("completed_by_id", sa.UUID()),
        sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("verification_status", sa.String(20), server_default="unverified", nullable=False), *_timestamps(),
        sa.CheckConstraint("status IN ('pending', 'in_progress', 'completed', 'cancelled')", name="ck_exit_clearance_status"),
        sa.CheckConstraint("verification_status IN ('unverified', 'verified', 'exceptions')", name="ck_exit_clearance_verification"),
        sa.CheckConstraint("(status = 'completed') = (completed_at IS NOT NULL AND completed_by_id IS NOT NULL)", name="ck_exit_clearance_completion"),
        sa.ForeignKeyConstraint(["employee_id"], ["public.employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["opened_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["completed_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_employee_exit_clearances"), schema="public")
    op.create_index("ix_exit_clearance_status", "employee_exit_clearances", ["status"], schema="public")
    op.create_index("uq_exit_clearance_open_employee", "employee_exit_clearances", ["employee_id"], unique=True,
        postgresql_where=sa.text("status IN ('pending', 'in_progress')"), schema="public")

    op.create_table("workflow_approvals", _id(),
        sa.Column("entity_type", sa.String(40), nullable=False), sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("required_capability", sa.String(80), nullable=False), sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("requested_by_id", sa.UUID(), nullable=False), sa.Column("decided_by_id", sa.UUID()),
        sa.Column("decided_at", sa.DateTime(timezone=True)), sa.Column("decision_reason_code", sa.String(40)), *_timestamps(),
        sa.CheckConstraint("entity_type IN ('asset_registration', 'allocation', 'return', 'disposal')", name="ck_workflow_approvals_entity_type"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="ck_workflow_approvals_status"),
        sa.CheckConstraint("length(trim(required_capability)) > 0", name="ck_workflow_approvals_capability_nonempty"),
        sa.CheckConstraint("decided_by_id IS NULL OR requested_by_id <> decided_by_id", name="ck_workflow_approvals_no_self_approval"),
        sa.CheckConstraint("(status IN ('approved', 'rejected')) = (decided_at IS NOT NULL AND decided_by_id IS NOT NULL)", name="ck_workflow_approvals_decision"),
        sa.CheckConstraint("decision_reason_code IS NULL OR length(trim(decision_reason_code)) > 0", name="ck_workflow_approvals_reason_nonempty"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_approvals"), schema="public")
    op.create_index("ix_workflow_approvals_status_created", "workflow_approvals", ["status", "created_at"], schema="public")
    op.create_index("ix_workflow_approvals_entity", "workflow_approvals", ["entity_type", "entity_id"], schema="public")
    op.create_index("uq_workflow_approvals_pending_capability", "workflow_approvals", ["entity_type", "entity_id", "required_capability"], unique=True,
        postgresql_where=sa.text("status = 'pending'"), schema="public")

    op.create_table("inventory_notifications", _id(),
        sa.Column("event_type", sa.String(40), nullable=False), sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False), sa.Column("recipient_user_id", sa.UUID()),
        sa.Column("status", sa.String(20), server_default="pending_policy", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("event_type IN ('registration_pending', 'approval_pending', 'return_outstanding', 'repair_updated', 'information_missing', 'warranty_reminder')", name="ck_inventory_notifications_event_type"),
        sa.CheckConstraint("entity_type IN ('receipt', 'allocation', 'inventory_return', 'asset_repair', 'employee_exit_clearance', 'disposal_request')", name="ck_inventory_notifications_entity_type"),
        sa.CheckConstraint("status IN ('pending_policy', 'ready', 'read', 'suppressed')", name="ck_inventory_notifications_status"),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_notifications"), schema="public")
    op.create_index("ix_inventory_notifications_recipient_status", "inventory_notifications", ["recipient_user_id", "status", "created_at"], schema="public")

    for table in ("allocations", "asset_repairs", "disposal_requests", "employee_exit_clearances", "workflow_approvals", "inventory_returns"):
        op.execute(f"CREATE TRIGGER {table}_set_updated_at BEFORE UPDATE ON public.{table} FOR EACH ROW EXECUTE FUNCTION public.inventory_aios_set_updated_at()")


def downgrade() -> None:
    op.execute("DO $block$ BEGIN IF " + " OR ".join(
        f"EXISTS (SELECT 1 FROM public.{table} LIMIT 1)" for table in (
            "allocations", "allocation_lines", "inventory_returns", "asset_repairs",
            "disposal_requests", "employee_exit_clearances", "workflow_approvals", "inventory_notifications",
        )
    ) + " OR EXISTS (SELECT 1 FROM public.audit_events WHERE previous_values IS NOT NULL OR updated_values IS NOT NULL)"
      + " THEN RAISE EXCEPTION 'cannot downgrade populated inventory workflow tables or audit values'; END IF; END; $block$")
    for table in ("allocations", "asset_repairs", "disposal_requests", "employee_exit_clearances", "workflow_approvals", "inventory_returns"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_set_updated_at ON public.{table}")
    for index, table in (
        ("ix_inventory_notifications_recipient_status", "inventory_notifications"),
        ("uq_workflow_approvals_pending_capability", "workflow_approvals"),
        ("ix_workflow_approvals_entity", "workflow_approvals"),
        ("ix_workflow_approvals_status_created", "workflow_approvals"),
        ("uq_exit_clearance_open_employee", "employee_exit_clearances"),
        ("ix_exit_clearance_status", "employee_exit_clearances"),
        ("uq_disposal_requests_open_asset", "disposal_requests"),
        ("uq_asset_repairs_one_open", "asset_repairs"), ("ix_asset_repairs_asset_status", "asset_repairs"),
        ("ix_inventory_returns_line_status", "inventory_returns"),
        ("uq_allocation_lines_active_asset", "allocation_lines"), ("ix_allocation_lines_allocation", "allocation_lines"),
        ("ix_allocations_employee_status", "allocations"),
    ):
        op.drop_index(index, table_name=table, schema="public")
    for table in ("inventory_notifications", "workflow_approvals", "employee_exit_clearances", "disposal_requests", "asset_repairs", "inventory_returns", "allocation_lines", "allocations"):
        op.drop_table(table, schema="public")
    op.drop_constraint("ck_audit_events_updated_values_object", "audit_events", schema="public", type_="check")
    op.drop_constraint("ck_audit_events_previous_values_object", "audit_events", schema="public", type_="check")
    op.execute("ALTER TABLE public.audit_events DROP COLUMN updated_values")
    op.execute("ALTER TABLE public.audit_events DROP COLUMN previous_values")
