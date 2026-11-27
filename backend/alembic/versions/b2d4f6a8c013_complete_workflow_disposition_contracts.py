"""Add repair detail and quarantined quantity disposition contracts.

Revision ID: b2d4f6a8c013
Revises: a1c7e3052b94
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b2d4f6a8c013"
down_revision: Union[str, None] = "a1c7e3052b94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AUDIT_FUNCTION = r"""
CREATE OR REPLACE FUNCTION public.inventory_aios_audit_values_are_valid(input_value jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog
AS $function$
DECLARE field_name text; field_value jsonb; numeric_value numeric;
BEGIN
    IF input_value IS NULL OR pg_catalog.jsonb_typeof(input_value) IS DISTINCT FROM 'object' THEN RETURN FALSE; END IF;
    FOR field_name, field_value IN SELECT key, value FROM pg_catalog.jsonb_each(input_value) LOOP
        IF field_name IN ('lifecycle_status','allocation_status','approval_status','clearance_status',
                          'verification_status','receipt_status','registration_status','condition',
                          'repair_status','disposal_status','disposition_status') THEN
            IF pg_catalog.jsonb_typeof(field_value) IS DISTINCT FROM 'string' THEN RETURN FALSE; END IF;
            IF field_name = 'lifecycle_status' AND field_value #>> ARRAY[]::text[] NOT IN ('available','allocated','repair','damaged','disposed') THEN RETURN FALSE; END IF;
            IF field_name = 'allocation_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','approved','rejected','issued','cancelled','partially_returned','returned') THEN RETURN FALSE; END IF;
            IF field_name = 'approval_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','approved','rejected','cancelled','completed') THEN RETURN FALSE; END IF;
            IF field_name = 'clearance_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','in_progress','completed','cancelled') THEN RETURN FALSE; END IF;
            IF field_name = 'verification_status' AND field_value #>> ARRAY[]::text[] NOT IN ('unverified','verified','exceptions') THEN RETURN FALSE; END IF;
            IF field_name = 'receipt_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','approved','rejected','registered') THEN RETURN FALSE; END IF;
            IF field_name = 'registration_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','approved','rejected','registered','cancelled') THEN RETURN FALSE; END IF;
            IF field_name = 'condition' AND field_value #>> ARRAY[]::text[] NOT IN ('good','repair','damaged','unknown') THEN RETURN FALSE; END IF;
            IF field_name = 'repair_status' AND field_value #>> ARRAY[]::text[] NOT IN ('reported','in_progress','completed','cancelled') THEN RETURN FALSE; END IF;
            IF field_name = 'disposal_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','approved','rejected','completed','cancelled') THEN RETURN FALSE; END IF;
            IF field_name = 'disposition_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','approved','rejected','completed') THEN RETURN FALSE; END IF;
        ELSIF field_name = 'product_active' THEN
            IF pg_catalog.jsonb_typeof(field_value) IS DISTINCT FROM 'boolean' THEN RETURN FALSE; END IF;
        ELSIF field_name = 'location_id' THEN
            IF pg_catalog.jsonb_typeof(field_value) IS DISTINCT FROM 'string' OR (field_value #>> ARRAY[]::text[]) !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN RETURN FALSE; END IF;
        ELSIF field_name IN ('quantity','reserved','returned_quantity','on_hand','quarantined') THEN
            IF pg_catalog.jsonb_typeof(field_value) NOT IN ('number','string') OR (field_value #>> ARRAY[]::text[]) !~ '^(0|[1-9][0-9]{0,11})(\.[0-9]{1,3})?$' THEN RETURN FALSE; END IF;
            numeric_value := (field_value #>> ARRAY[]::text[])::numeric;
            IF numeric_value < 0 OR numeric_value > 99999999999.999 THEN RETURN FALSE; END IF;
        ELSE RETURN FALSE;
        END IF;
    END LOOP;
    RETURN TRUE;
EXCEPTION WHEN others THEN RETURN FALSE;
END;
$function$
"""


def upgrade() -> None:
    op.add_column("inventory_balances", sa.Column("quarantined", sa.Numeric(14, 3), server_default="0", nullable=False), schema="public")
    op.drop_constraint("ck_inventory_balances_reserved_valid", "inventory_balances", schema="public", type_="check")
    op.create_check_constraint("ck_inventory_balances_reserved_valid", "inventory_balances",
        "reserved >= 0 AND quarantined >= 0 AND reserved + quarantined <= on_hand", schema="public")

    for name in ("on_hand_delta", "reserved_delta", "quarantined_delta"):
        op.add_column("inventory_movements", sa.Column(name, sa.Numeric(14, 3), server_default="0", nullable=False), schema="public")
    op.execute("UPDATE public.inventory_movements SET on_hand_delta = CASE WHEN movement_type IN ('receipt','adjustment','disposal') THEN quantity_delta ELSE 0 END, reserved_delta = CASE WHEN movement_type = 'allocation' THEN -quantity_delta WHEN movement_type = 'return' THEN -quantity_delta ELSE 0 END")
    op.drop_constraint("ck_inventory_movements_nonzero_delta", "inventory_movements", schema="public", type_="check")
    op.create_check_constraint("ck_inventory_movements_nonzero_delta", "inventory_movements",
        "quantity_delta <> 0 OR on_hand_delta <> 0 OR reserved_delta <> 0 OR quarantined_delta <> 0", schema="public")
    op.drop_constraint("ck_inventory_movements_type", "inventory_movements", schema="public", type_="check")
    op.create_check_constraint("ck_inventory_movements_type", "inventory_movements",
        "movement_type IN ('receipt','adjustment','allocation','return','disposal','quarantine','quarantine_release','quarantine_disposal')", schema="public")

    op.add_column("inventory_returns", sa.Column("resolved_quantity", sa.Numeric(14, 3), server_default="0", nullable=False), schema="public")
    op.create_check_constraint("ck_inventory_returns_resolved_quantity", "inventory_returns",
        "resolved_quantity >= 0 AND resolved_quantity <= quantity", schema="public")

    op.add_column("asset_repairs", sa.Column("issue_details", sa.Text(), nullable=True), schema="public")
    op.add_column("asset_repairs", sa.Column("repair_provider", sa.String(200), nullable=True), schema="public")
    op.add_column("asset_repairs", sa.Column("cost_amount", sa.Numeric(14, 2), nullable=True), schema="public")
    op.add_column("asset_repairs", sa.Column("cost_currency", sa.String(3), nullable=True), schema="public")
    op.add_column("asset_repairs", sa.Column("completion_condition", sa.String(20), nullable=True), schema="public")
    op.add_column("asset_repairs", sa.Column("completion_notes", sa.Text(), nullable=True), schema="public")
    op.create_check_constraint("ck_asset_repairs_issue_details_nonempty", "asset_repairs", "issue_details IS NULL OR length(trim(issue_details)) > 0", schema="public")
    op.create_check_constraint("ck_asset_repairs_cost_nonnegative", "asset_repairs", "cost_amount IS NULL OR cost_amount >= 0", schema="public")
    op.create_check_constraint("ck_asset_repairs_cost_currency_pair", "asset_repairs", "(cost_amount IS NULL) = (cost_currency IS NULL)", schema="public")
    op.create_check_constraint("ck_asset_repairs_cost_currency_code", "asset_repairs", "cost_currency IS NULL OR cost_currency ~ '^[A-Z]{3}$'", schema="public")
    op.create_check_constraint("ck_asset_repairs_completion_condition", "asset_repairs", "completion_condition IS NULL OR completion_condition IN ('good','damaged')", schema="public")
    op.create_check_constraint("ck_asset_repairs_completion_condition_required", "asset_repairs", "completion_condition IS NULL OR status = 'completed'", schema="public")

    op.add_column("disposal_requests", sa.Column("reason_code", sa.String(40), nullable=True), schema="public")
    op.add_column("disposal_requests", sa.Column("condition", sa.String(20), nullable=True), schema="public")
    op.add_column("disposal_requests", sa.Column("completed_by_id", sa.UUID(), nullable=True), schema="public")
    op.add_column("disposal_requests", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True), schema="public")
    op.create_foreign_key("fk_disposal_requests_completed_by", "disposal_requests", "users", ["completed_by_id"], ["id"], source_schema="public", referent_schema="public", ondelete="RESTRICT")
    op.create_check_constraint("ck_disposal_requests_reason_nonempty", "disposal_requests", "reason_code IS NULL OR length(trim(reason_code)) > 0", schema="public")
    op.create_check_constraint("ck_disposal_requests_condition", "disposal_requests", "condition IS NULL OR condition IN ('good','repair','damaged','unknown')", schema="public")
    op.create_check_constraint("ck_disposal_requests_completion", "disposal_requests", "(completed_at IS NULL) = (completed_by_id IS NULL)", schema="public")

    op.create_table("quantity_disposition_requests",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("inventory_return_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("disposition", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("requested_by_id", sa.UUID(), nullable=False),
        sa.Column("idempotency_request_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_quantity_disposition_quantity_positive"),
        sa.CheckConstraint("disposition IN ('release','dispose')", name="ck_quantity_disposition_kind"),
        sa.CheckConstraint("status IN ('pending','approved','rejected','completed')", name="ck_quantity_disposition_status"),
        sa.ForeignKeyConstraint(["inventory_return_id"], ["public.inventory_returns.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["public.users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["idempotency_request_id"], ["public.idempotency_requests.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_quantity_disposition_requests"),
        sa.UniqueConstraint("idempotency_request_id", name="uq_quantity_disposition_requests_idempotency_request_id"),
        schema="public")
    op.create_index("ix_quantity_disposition_return_status", "quantity_disposition_requests", ["inventory_return_id", "status"], schema="public")
    op.execute("CREATE TRIGGER quantity_disposition_requests_set_updated_at BEFORE UPDATE ON public.quantity_disposition_requests FOR EACH ROW EXECUTE FUNCTION public.inventory_aios_set_updated_at()")

    op.drop_constraint("ck_workflow_approvals_entity_type", "workflow_approvals", schema="public", type_="check")
    op.create_check_constraint("ck_workflow_approvals_entity_type", "workflow_approvals",
        "entity_type IN ('product','receiving','asset_registration','quantity_registration','allocation','return','disposal','repair','exit_clearance','quantity_disposition')", schema="public")
    op.execute(_AUDIT_FUNCTION)


def downgrade() -> None:
    op.execute("DO $block$ BEGIN IF EXISTS (SELECT 1 FROM public.quantity_disposition_requests LIMIT 1) OR EXISTS (SELECT 1 FROM public.inventory_balances WHERE quarantined <> 0) OR EXISTS (SELECT 1 FROM public.inventory_returns WHERE resolved_quantity <> 0) OR EXISTS (SELECT 1 FROM public.inventory_movements WHERE movement_type IN ('quarantine','quarantine_release','quarantine_disposal')) OR EXISTS (SELECT 1 FROM public.audit_events WHERE COALESCE(previous_values, '{}'::jsonb) ?| ARRAY['repair_status','disposal_status','disposition_status','quarantined'] OR COALESCE(updated_values, '{}'::jsonb) ?| ARRAY['repair_status','disposal_status','disposition_status','quarantined']) THEN RAISE EXCEPTION 'cannot downgrade populated workflow disposition state'; END IF; END; $block$")
    op.drop_constraint("ck_workflow_approvals_entity_type", "workflow_approvals", schema="public", type_="check")
    op.create_check_constraint("ck_workflow_approvals_entity_type", "workflow_approvals",
        "entity_type IN ('product','receiving','asset_registration','quantity_registration','allocation','return','disposal','repair','exit_clearance')", schema="public")
    op.execute("DROP TRIGGER IF EXISTS quantity_disposition_requests_set_updated_at ON public.quantity_disposition_requests")
    op.drop_index("ix_quantity_disposition_return_status", table_name="quantity_disposition_requests", schema="public")
    op.drop_table("quantity_disposition_requests", schema="public")
    op.execute("""CREATE OR REPLACE FUNCTION public.inventory_aios_audit_values_are_valid(input_value jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog AS $function$
DECLARE field_name text; field_value jsonb; numeric_value numeric;
BEGIN
 IF input_value IS NULL OR pg_catalog.jsonb_typeof(input_value) IS DISTINCT FROM 'object' THEN RETURN FALSE; END IF;
 FOR field_name, field_value IN SELECT key, value FROM pg_catalog.jsonb_each(input_value) LOOP
  IF field_name IN ('lifecycle_status','allocation_status','approval_status','clearance_status','verification_status','receipt_status','registration_status','condition') THEN
   IF pg_catalog.jsonb_typeof(field_value) IS DISTINCT FROM 'string' THEN RETURN FALSE; END IF;
   IF field_name='lifecycle_status' AND field_value #>> ARRAY[]::text[] NOT IN ('available','allocated','repair','damaged','disposed') THEN RETURN FALSE; END IF;
   IF field_name='allocation_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','approved','rejected','issued','cancelled','partially_returned','returned') THEN RETURN FALSE; END IF;
   IF field_name='approval_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','approved','rejected','cancelled') THEN RETURN FALSE; END IF;
   IF field_name='clearance_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','in_progress','completed','cancelled') THEN RETURN FALSE; END IF;
   IF field_name='verification_status' AND field_value #>> ARRAY[]::text[] NOT IN ('unverified','verified','exceptions') THEN RETURN FALSE; END IF;
   IF field_name='receipt_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','approved','rejected','registered') THEN RETURN FALSE; END IF;
   IF field_name='registration_status' AND field_value #>> ARRAY[]::text[] NOT IN ('pending','approved','rejected','registered','cancelled') THEN RETURN FALSE; END IF;
   IF field_name='condition' AND field_value #>> ARRAY[]::text[] NOT IN ('good','repair','damaged','unknown') THEN RETURN FALSE; END IF;
  ELSIF field_name='product_active' THEN IF pg_catalog.jsonb_typeof(field_value) IS DISTINCT FROM 'boolean' THEN RETURN FALSE; END IF;
  ELSIF field_name='location_id' THEN IF pg_catalog.jsonb_typeof(field_value) IS DISTINCT FROM 'string' OR (field_value #>> ARRAY[]::text[]) !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN RETURN FALSE; END IF;
  ELSIF field_name IN ('quantity','reserved','returned_quantity','on_hand') THEN
   IF pg_catalog.jsonb_typeof(field_value) NOT IN ('number','string') OR (field_value #>> ARRAY[]::text[]) !~ '^(0|[1-9][0-9]{0,11})(\\.[0-9]{1,3})?$' THEN RETURN FALSE; END IF;
   numeric_value := (field_value #>> ARRAY[]::text[])::numeric; IF numeric_value < 0 OR numeric_value > 99999999999.999 THEN RETURN FALSE; END IF;
  ELSE RETURN FALSE; END IF;
 END LOOP; RETURN TRUE;
EXCEPTION WHEN others THEN RETURN FALSE; END; $function$""")
    for name in ("ck_disposal_requests_completion", "ck_disposal_requests_condition", "ck_disposal_requests_reason_nonempty"):
        op.drop_constraint(name, "disposal_requests", schema="public", type_="check")
    op.drop_constraint("fk_disposal_requests_completed_by", "disposal_requests", schema="public", type_="foreignkey")
    for name in ("completed_at", "completed_by_id", "condition", "reason_code"):
        op.drop_column("disposal_requests", name, schema="public")
    for name in ("ck_asset_repairs_completion_condition_required", "ck_asset_repairs_completion_condition", "ck_asset_repairs_cost_currency_code", "ck_asset_repairs_cost_currency_pair", "ck_asset_repairs_cost_nonnegative", "ck_asset_repairs_issue_details_nonempty"):
        op.drop_constraint(name, "asset_repairs", schema="public", type_="check")
    for name in ("completion_notes", "completion_condition", "cost_currency", "cost_amount", "repair_provider", "issue_details"):
        op.drop_column("asset_repairs", name, schema="public")
    op.drop_constraint("ck_inventory_returns_resolved_quantity", "inventory_returns", schema="public", type_="check")
    op.drop_column("inventory_returns", "resolved_quantity", schema="public")
    for name in ("ck_inventory_movements_type", "ck_inventory_movements_nonzero_delta"):
        op.drop_constraint(name, "inventory_movements", schema="public", type_="check")
    op.create_check_constraint("ck_inventory_movements_nonzero_delta", "inventory_movements", "quantity_delta <> 0", schema="public")
    op.create_check_constraint("ck_inventory_movements_type", "inventory_movements", "movement_type IN ('receipt','adjustment','allocation','return','disposal')", schema="public")
    for name in ("quarantined_delta", "reserved_delta", "on_hand_delta"):
        op.drop_column("inventory_movements", name, schema="public")
    op.drop_constraint("ck_inventory_balances_reserved_valid", "inventory_balances", schema="public", type_="check")
    op.create_check_constraint("ck_inventory_balances_reserved_valid", "inventory_balances", "reserved >= 0 AND reserved <= on_hand", schema="public")
    op.drop_column("inventory_balances", "quarantined", schema="public")
