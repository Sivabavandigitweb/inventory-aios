"""add employee source mapping and core inventory foundation

Revision ID: 4b6f10a2c903
Revises: 0ea2d9c71b45
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "4b6f10a2c903"
down_revision: Union[str, None] = "0ea2d9c71b45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def upgrade() -> None:
    op.create_table("idempotency_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("principal_id", sa.UUID(), nullable=False),
        sa.Column("operation_scope", sa.String(200), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("response_status", sa.SmallInteger()),
        sa.Column("resource_type", sa.String(80)),
        sa.Column("resource_id", sa.UUID()),
        sa.Column("completed_at", sa.DateTime(timezone=True)), *_timestamps(),
        sa.CheckConstraint("length(trim(operation_scope)) > 0", name="ck_idempotency_requests_scope_nonempty"),
        sa.CheckConstraint("length(trim(idempotency_key)) > 0", name="ck_idempotency_requests_key_nonempty"),
        sa.CheckConstraint("request_fingerprint ~ '^[0-9a-f]{64}$'", name="ck_idempotency_requests_fingerprint_sha256"),
        sa.CheckConstraint("status IN ('processing', 'succeeded')", name="ck_idempotency_requests_status"),
        sa.CheckConstraint("(status = 'processing' AND response_status IS NULL AND resource_type IS NULL AND resource_id IS NULL AND completed_at IS NULL) OR (status = 'succeeded' AND response_status IS NOT NULL AND response_status BETWEEN 200 AND 299 AND completed_at IS NOT NULL)", name="ck_idempotency_requests_completion"),
        sa.CheckConstraint("(resource_type IS NULL) = (resource_id IS NULL) AND (resource_type IS NULL OR length(trim(resource_type)) > 0)", name="ck_idempotency_requests_resource_pair"),
        sa.ForeignKeyConstraint(["principal_id"], ["public.users.id"], name="fk_idempotency_requests_principal_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_requests"),
        sa.UniqueConstraint("principal_id", "operation_scope", "idempotency_key", name="uq_idempotency_requests_principal_scope_key"), schema="public")
    op.create_index("ix_idempotency_requests_principal_status", "idempotency_requests", ["principal_id", "status"], schema="public")

    op.create_table("inventory_products",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False), sa.Column("sku", sa.String(80)),
        sa.Column("name", sa.String(200), nullable=False), sa.Column("brand", sa.String(150)),
        sa.Column("model", sa.String(150)), sa.Column("specifications", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False), *_timestamps(),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_inventory_products_name_nonempty"),
        sa.CheckConstraint("sku IS NULL OR length(trim(sku)) > 0", name="ck_inventory_products_sku_nonempty"),
        sa.CheckConstraint("jsonb_typeof(specifications) = 'object'", name="ck_inventory_products_specifications_object"),
        sa.ForeignKeyConstraint(["category_id"], ["public.asset_categories.id"], name="fk_inventory_products_category_id_asset_categories", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_products"), schema="public")
    op.create_index("ix_inventory_products_category_active", "inventory_products", ["category_id", "active"], schema="public")

    op.create_table("receipts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_by_id", sa.UUID(), nullable=False), sa.Column("location_id", sa.UUID(), nullable=False),
        sa.Column("supplier_id", sa.UUID()), sa.Column("external_reference", sa.String(150)), sa.Column("notes", sa.Text()), *_timestamps(),
        sa.CheckConstraint("external_reference IS NULL OR length(trim(external_reference)) > 0", name="ck_receipts_external_reference_nonempty"),
        sa.ForeignKeyConstraint(["received_by_id"], ["public.users.id"], name="fk_receipts_received_by_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["public.locations.id"], name="fk_receipts_location_id_locations", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_id"], ["public.suppliers.id"], name="fk_receipts_supplier_id_suppliers", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_receipts"), schema="public")
    op.create_index("ix_receipts_received_at", "receipts", ["received_at"], schema="public")
    op.create_index("ix_receipts_received_by_id", "receipts", ["received_by_id"], schema="public")
    op.create_index("ix_receipts_location_received_at", "receipts", ["location_id", "received_at"], schema="public")

    op.create_table("receipt_lines",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("receipt_id", sa.UUID(), nullable=False), sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False), sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("tracking_mode", sa.String(20), nullable=False), sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_receipt_lines_quantity_positive"),
        sa.CheckConstraint("length(trim(unit)) > 0", name="ck_receipt_lines_unit_nonempty"),
        sa.CheckConstraint("tracking_mode IN ('individual', 'quantity')", name="ck_receipt_lines_tracking_mode"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'registered')", name="ck_receipt_lines_status"),
        sa.ForeignKeyConstraint(["receipt_id"], ["public.receipts.id"], name="fk_receipt_lines_receipt_id_receipts", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_id"], ["public.inventory_products.id"], name="fk_receipt_lines_product_id_inventory_products", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_receipt_lines"), schema="public")
    op.create_index("ix_receipt_lines_receipt", "receipt_lines", ["receipt_id"], schema="public")
    op.create_index("ix_receipt_lines_product", "receipt_lines", ["product_id"], schema="public")

    op.create_table("tracked_assets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False), sa.Column("receipt_line_id", sa.UUID()),
        sa.Column("location_id", sa.UUID(), nullable=False), sa.Column("asset_number", sa.String(100)),
        sa.Column("serial_number", sa.String(150)), sa.Column("lifecycle_status", sa.String(20), nullable=False),
        sa.Column("condition", sa.String(40)), *_timestamps(),
        sa.CheckConstraint("lifecycle_status IN ('available', 'allocated', 'repair', 'damaged', 'disposed')", name="ck_tracked_assets_lifecycle_status"),
        sa.CheckConstraint("asset_number IS NULL OR length(trim(asset_number)) > 0", name="ck_tracked_assets_asset_number_nonempty"),
        sa.ForeignKeyConstraint(["product_id"], ["public.inventory_products.id"], name="fk_tracked_assets_product_id_inventory_products", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["receipt_line_id"], ["public.receipt_lines.id"], name="fk_tracked_assets_receipt_line_id_receipt_lines", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["public.locations.id"], name="fk_tracked_assets_location_id_locations", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_tracked_assets"), schema="public")
    op.create_index("uq_tracked_assets_asset_number", "tracked_assets", ["asset_number"], unique=True, schema="public", postgresql_where=sa.text("asset_number IS NOT NULL"))
    op.create_index("ix_tracked_assets_product_status", "tracked_assets", ["product_id", "lifecycle_status"], schema="public")
    op.create_index("ix_tracked_assets_location_status", "tracked_assets", ["location_id", "lifecycle_status"], schema="public")

    op.create_table("quantity_inventory_lots",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False), sa.Column("location_id", sa.UUID(), nullable=False),
        sa.Column("receipt_line_id", sa.UUID()), sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False), *_timestamps(),
        sa.CheckConstraint("length(trim(unit)) > 0", name="ck_quantity_inventory_lots_unit_nonempty"),
        sa.CheckConstraint("quantity >= 0", name="ck_quantity_inventory_lots_quantity_nonnegative"),
        sa.ForeignKeyConstraint(["product_id"], ["public.inventory_products.id"], name="fk_quantity_inventory_lots_product_id_inventory_products", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["public.locations.id"], name="fk_quantity_inventory_lots_location_id_locations", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["receipt_line_id"], ["public.receipt_lines.id"], name="fk_quantity_inventory_lots_receipt_line_id_receipt_lines", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_quantity_inventory_lots"), schema="public")
    op.create_index("ix_quantity_inventory_lots_product_location_unit", "quantity_inventory_lots", ["product_id", "location_id", "unit"], schema="public")

    op.create_table("inventory_balances",
        sa.Column("product_id", sa.UUID(), nullable=False), sa.Column("location_id", sa.UUID(), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False), sa.Column("on_hand", sa.Numeric(14, 3), server_default="0", nullable=False),
        sa.Column("reserved", sa.Numeric(14, 3), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("length(trim(unit)) > 0", name="ck_inventory_balances_unit_nonempty"),
        sa.CheckConstraint("on_hand >= 0", name="ck_inventory_balances_on_hand_nonnegative"),
        sa.CheckConstraint("reserved >= 0 AND reserved <= on_hand", name="ck_inventory_balances_reserved_valid"),
        sa.ForeignKeyConstraint(["product_id"], ["public.inventory_products.id"], name="fk_inventory_balances_product_id_inventory_products", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["public.locations.id"], name="fk_inventory_balances_location_id_locations", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("product_id", "location_id", "unit", name="pk_inventory_balances"), schema="public")
    op.create_index("ix_inventory_balances_location_product", "inventory_balances", ["location_id", "product_id"], schema="public")

    op.create_table("inventory_movements",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("product_id", sa.UUID(), nullable=False), sa.Column("location_id", sa.UUID(), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False), sa.Column("quantity_delta", sa.Numeric(14, 3), nullable=False),
        sa.Column("movement_type", sa.String(30), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor_user_id", sa.UUID()), sa.Column("idempotency_request_id", sa.UUID(), nullable=False),
        sa.Column("reference_type", sa.String(60)), sa.Column("reference_id", sa.UUID()),
        sa.CheckConstraint("quantity_delta <> 0", name="ck_inventory_movements_nonzero_delta"),
        sa.CheckConstraint("length(trim(unit)) > 0", name="ck_inventory_movements_unit_nonempty"),
        sa.CheckConstraint("movement_type IN ('receipt', 'adjustment', 'allocation', 'return', 'disposal')", name="ck_inventory_movements_type"),
        sa.CheckConstraint("(reference_type IS NULL) = (reference_id IS NULL)", name="ck_inventory_movements_reference_pair"),
        sa.ForeignKeyConstraint(["product_id"], ["public.inventory_products.id"], name="fk_inventory_movements_product_id_inventory_products", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["location_id"], ["public.locations.id"], name="fk_inventory_movements_location_id_locations", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["public.users.id"], name="fk_inventory_movements_actor_user_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["idempotency_request_id"], ["public.idempotency_requests.id"], name="fk_inventory_movements_idem_request", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_inventory_movements"), sa.UniqueConstraint("idempotency_request_id", name="uq_inventory_movements_idempotency_request_id"), schema="public")
    op.create_index("ix_inventory_movements_product_location_time", "inventory_movements", ["product_id", "location_id", "occurred_at"], schema="public")

    op.create_table("asset_registration_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tracked_asset_id", sa.UUID(), nullable=False), sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("actor_user_id", sa.UUID()), sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.CheckConstraint("event_type IN ('pending', 'approved', 'registered', 'rejected')", name="ck_asset_registration_events_type"),
        sa.CheckConstraint("jsonb_typeof(details) = 'object'", name="ck_asset_registration_events_details_object"),
        sa.ForeignKeyConstraint(["tracked_asset_id"], ["public.tracked_assets.id"], name="fk_asset_registration_events_tracked_asset_id_tracked_assets", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["public.users.id"], name="fk_asset_registration_events_actor_user_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_asset_registration_events"), schema="public")
    op.create_index("ix_asset_registration_events_asset_time", "asset_registration_events", ["tracked_asset_id", "occurred_at"], schema="public")

    op.create_table("employee_source_identities",
        sa.Column("source_key", sa.String(100), nullable=False), sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("employee_id", sa.UUID(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("length(trim(source_key)) > 0", name="ck_employee_source_identities_source_nonempty"),
        sa.CheckConstraint("length(trim(external_id)) > 0", name="ck_employee_source_identities_external_nonempty"),
        sa.ForeignKeyConstraint(["employee_id"], ["public.employees.id"], name="fk_employee_source_identities_employee_id_employees", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("source_key", "external_id", name="pk_employee_source_identities"),
        sa.UniqueConstraint("employee_id", name="uq_employee_source_identities_employee_id"), schema="public")

    op.create_table("employee_sync_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_key", sa.String(100), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("dry_run", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("read_count", sa.Integer(), server_default="0", nullable=False), sa.Column("inserted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_count", sa.Integer(), server_default="0", nullable=False), sa.Column("unchanged_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("conflict_count", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("status IN ('running', 'succeeded', 'failed', 'dry_run')", name="ck_employee_sync_runs_status"),
        sa.CheckConstraint("read_count >= 0 AND inserted_count >= 0 AND updated_count >= 0 AND unchanged_count >= 0 AND conflict_count >= 0", name="ck_employee_sync_runs_counts_nonnegative"),
        sa.PrimaryKeyConstraint("id", name="pk_employee_sync_runs"), schema="public")
    op.create_index("ix_employee_sync_runs_source_started", "employee_sync_runs", ["source_key", "started_at"], schema="public")

    for table in ("idempotency_requests", "inventory_products", "receipts", "tracked_assets", "quantity_inventory_lots", "inventory_balances"):
        op.execute(f"CREATE TRIGGER {table}_set_updated_at BEFORE UPDATE ON public.{table} FOR EACH ROW EXECUTE FUNCTION public.inventory_aios_set_updated_at()")


def downgrade() -> None:
    tables = ("idempotency_requests", "inventory_products", "receipts", "receipt_lines", "tracked_assets", "quantity_inventory_lots",
              "inventory_balances", "inventory_movements", "asset_registration_events",
              "employee_source_identities", "employee_sync_runs")
    op.execute("DO $block$ BEGIN IF " + " OR ".join(
        f"EXISTS (SELECT 1 FROM public.{table} LIMIT 1)" for table in tables
    ) + " THEN RAISE EXCEPTION 'cannot downgrade populated employee-sync or inventory tables'; END IF; END; $block$")
    for table in ("inventory_products", "receipts", "tracked_assets", "quantity_inventory_lots", "inventory_balances"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_set_updated_at ON public.{table}")
    op.execute("DROP TRIGGER IF EXISTS idempotency_requests_set_updated_at ON public.idempotency_requests")
    for name, table in (
        ("ix_employee_sync_runs_source_started", "employee_sync_runs"),
        ("ix_asset_registration_events_asset_time", "asset_registration_events"),
        ("ix_inventory_movements_product_location_time", "inventory_movements"),
        ("ix_inventory_balances_location_product", "inventory_balances"),
        ("ix_quantity_inventory_lots_product_location_unit", "quantity_inventory_lots"),
        ("ix_tracked_assets_location_status", "tracked_assets"), ("ix_tracked_assets_product_status", "tracked_assets"),
        ("uq_tracked_assets_asset_number", "tracked_assets"),
        ("ix_receipt_lines_product", "receipt_lines"), ("ix_receipt_lines_receipt", "receipt_lines"),
        ("ix_receipts_location_received_at", "receipts"), ("ix_receipts_received_by_id", "receipts"), ("ix_receipts_received_at", "receipts"),
        ("ix_inventory_products_category_active", "inventory_products"),
        ("ix_idempotency_requests_principal_status", "idempotency_requests"),
    ):
        op.drop_index(name, table_name=table, schema="public")
    for table in reversed(tables):
        op.drop_table(table, schema="public")
