"""Add registration requests and database-side audit value validation.

Revision ID: a1c7e3052b94
Revises: 9c81e247a610
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1c7e3052b94"
down_revision: Union[str, None] = "9c81e247a610"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AUDIT_FUNCTION = r"""
CREATE OR REPLACE FUNCTION public.inventory_aios_audit_values_are_valid(input_value jsonb)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog
AS $function$
DECLARE
    field_name text;
    field_value jsonb;
    numeric_value numeric;
BEGIN
    IF input_value IS NULL OR pg_catalog.jsonb_typeof(input_value) IS DISTINCT FROM 'object' THEN
        RETURN FALSE;
    END IF;
    FOR field_name, field_value IN SELECT key, value FROM pg_catalog.jsonb_each(input_value)
    LOOP
        IF field_name IN ('lifecycle_status', 'allocation_status', 'approval_status',
                          'clearance_status', 'verification_status', 'receipt_status',
                          'registration_status', 'condition') THEN
            IF pg_catalog.jsonb_typeof(field_value) IS DISTINCT FROM 'string' THEN RETURN FALSE; END IF;
            IF field_name = 'lifecycle_status' AND field_value #>> ARRAY[]::text[] NOT IN ('available','allocated','repair','damaged','disposed') THEN RETURN FALSE; END IF;
            IF field_name = 'allocation_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','approved','rejected','issued','cancelled','partially_returned','returned') THEN RETURN FALSE; END IF;
            IF field_name = 'approval_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','approved','rejected','cancelled') THEN RETURN FALSE; END IF;
            IF field_name = 'clearance_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','in_progress','completed','cancelled') THEN RETURN FALSE; END IF;
            IF field_name = 'verification_status' AND field_value #>> ARRAY[]::text[] NOT IN ('unverified','verified','exceptions') THEN RETURN FALSE; END IF;
            IF field_name = 'receipt_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','approved','rejected','registered') THEN RETURN FALSE; END IF;
            IF field_name = 'registration_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','approved','rejected','registered','cancelled') THEN RETURN FALSE; END IF;
            IF field_name = 'condition' AND field_value #>> ARRAY[]::text[] NOT IN ('good','repair','damaged','unknown') THEN RETURN FALSE; END IF;
        ELSIF field_name = 'product_active' THEN
            IF pg_catalog.jsonb_typeof(field_value) IS DISTINCT FROM 'boolean' THEN RETURN FALSE; END IF;
        ELSIF field_name = 'location_id' THEN
            IF pg_catalog.jsonb_typeof(field_value) IS DISTINCT FROM 'string'
               OR (field_value #>> ARRAY[]::text[]) !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN RETURN FALSE; END IF;
        ELSIF field_name IN ('quantity','reserved','returned_quantity','on_hand') THEN
            IF pg_catalog.jsonb_typeof(field_value) NOT IN ('number','string')
               OR (field_value #>> ARRAY[]::text[]) !~ '^(0|[1-9][0-9]{0,11})(\.[0-9]{1,3})?$' THEN RETURN FALSE; END IF;
            numeric_value := (field_value #>> ARRAY[]::text[])::numeric;
            IF numeric_value < 0 OR numeric_value > 99999999999.999 THEN RETURN FALSE; END IF;
        ELSE
            RETURN FALSE;
        END IF;
    END LOOP;
    RETURN TRUE;
EXCEPTION WHEN others THEN
    RETURN FALSE;
END;
$function$
"""


def upgrade() -> None:
    for table in ("inventory_products", "receipts", "tracked_assets", "quantity_inventory_lots"):
        op.add_column(table, sa.Column("idempotency_request_id", sa.UUID(), nullable=True), schema="public")
        op.create_foreign_key(f"fk_{table}_idempotency_request", table, "idempotency_requests",
            ["idempotency_request_id"], ["id"], source_schema="public", referent_schema="public", ondelete="RESTRICT")
        op.create_unique_constraint(f"uq_{table}_idempotency_request_id", table,
            ["idempotency_request_id"], schema="public")
    op.create_index("uq_inventory_products_sku", "inventory_products", ["sku"], unique=True,
        postgresql_where=sa.text("sku IS NOT NULL"), schema="public")

    op.drop_constraint("ck_workflow_approvals_entity_type", "workflow_approvals", schema="public", type_="check")
    op.create_check_constraint("ck_workflow_approvals_entity_type", "workflow_approvals",
        "entity_type IN ('product', 'receiving', 'asset_registration', 'quantity_registration', 'allocation', 'return', 'disposal', 'repair', 'exit_clearance')",
        schema="public")

    op.execute(_AUDIT_FUNCTION)
    op.drop_constraint("ck_audit_events_previous_values_object", "audit_events", schema="public", type_="check")
    op.drop_constraint("ck_audit_events_updated_values_object", "audit_events", schema="public", type_="check")
    op.create_check_constraint("ck_audit_events_previous_values_object", "audit_events",
        "previous_values IS NULL OR public.inventory_aios_audit_values_are_valid(previous_values)", schema="public")
    op.create_check_constraint("ck_audit_events_updated_values_object", "audit_events",
        "updated_values IS NULL OR public.inventory_aios_audit_values_are_valid(updated_values)", schema="public")

    op.create_table("asset_registration_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("receipt_line_id", sa.UUID(), nullable=False), sa.Column("asset_number", sa.String(100)),
        sa.Column("serial_number", sa.String(150)), sa.Column("condition", sa.String(40)),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("submitted_by_id", sa.UUID(), nullable=False), sa.Column("idempotency_request_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'registered', 'cancelled')", name="ck_asset_registration_requests_status"),
        sa.CheckConstraint("asset_number IS NULL OR length(trim(asset_number)) > 0", name="ck_asset_registration_requests_asset_number"),
        sa.ForeignKeyConstraint(["receipt_line_id"], ["public.receipt_lines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["idempotency_request_id"], ["public.idempotency_requests.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_asset_registration_requests"),
        sa.UniqueConstraint("idempotency_request_id", name="uq_asset_registration_requests_idempotency_request_id"), schema="public")
    op.create_index("ix_asset_registration_requests_receipt_line_status", "asset_registration_requests", ["receipt_line_id", "status"], schema="public")

    op.create_table("quantity_registration_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("receipt_line_id", sa.UUID(), nullable=False), sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False), sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("submitted_by_id", sa.UUID(), nullable=False), sa.Column("idempotency_request_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_quantity_registration_requests_quantity_positive"),
        sa.CheckConstraint("length(trim(unit)) > 0", name="ck_quantity_registration_requests_unit_nonempty"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected', 'registered', 'cancelled')", name="ck_quantity_registration_requests_status"),
        sa.ForeignKeyConstraint(["receipt_line_id"], ["public.receipt_lines.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["idempotency_request_id"], ["public.idempotency_requests.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_quantity_registration_requests"),
        sa.UniqueConstraint("idempotency_request_id", name="uq_quantity_registration_requests_idempotency_request_id"), schema="public")
    op.create_index("ix_quantity_registration_requests_receipt_line_status", "quantity_registration_requests", ["receipt_line_id", "status"], schema="public")
    for table in ("asset_registration_requests", "quantity_registration_requests"):
        op.execute(f"CREATE TRIGGER {table}_set_updated_at BEFORE UPDATE ON public.{table} FOR EACH ROW EXECUTE FUNCTION public.inventory_aios_set_updated_at()")


def downgrade() -> None:
    op.execute("DO $block$ BEGIN IF EXISTS (SELECT 1 FROM public.asset_registration_requests LIMIT 1) OR EXISTS (SELECT 1 FROM public.quantity_registration_requests LIMIT 1) OR EXISTS (SELECT 1 FROM public.audit_events WHERE previous_values IS NOT NULL OR updated_values IS NOT NULL) THEN RAISE EXCEPTION 'cannot downgrade populated registration requests or audit values'; END IF; END; $block$")
    for table in ("asset_registration_requests", "quantity_registration_requests"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_set_updated_at ON public.{table}")
    op.drop_index("ix_quantity_registration_requests_receipt_line_status", table_name="quantity_registration_requests", schema="public")
    op.drop_index("ix_asset_registration_requests_receipt_line_status", table_name="asset_registration_requests", schema="public")
    op.drop_table("quantity_registration_requests", schema="public")
    op.drop_table("asset_registration_requests", schema="public")
    op.drop_constraint("ck_audit_events_updated_values_object", "audit_events", schema="public", type_="check")
    op.drop_constraint("ck_audit_events_previous_values_object", "audit_events", schema="public", type_="check")
    op.execute("ALTER TABLE public.workflow_approvals DROP CONSTRAINT ck_workflow_approvals_entity_type")
    op.create_check_constraint("ck_workflow_approvals_entity_type", "workflow_approvals",
        "entity_type IN ('asset_registration', 'allocation', 'return', 'disposal')", schema="public")
    op.drop_index("uq_inventory_products_sku", table_name="inventory_products", schema="public")
    for table in reversed(("inventory_products", "receipts", "tracked_assets", "quantity_inventory_lots")):
        op.drop_constraint(f"uq_{table}_idempotency_request_id", table, schema="public", type_="unique")
        op.drop_constraint(f"fk_{table}_idempotency_request", table, schema="public", type_="foreignkey")
        op.drop_column(table, "idempotency_request_id", schema="public")
    op.execute("DROP FUNCTION public.inventory_aios_audit_values_are_valid(jsonb)")
