"""Add dedicated append-only bootstrap attribution records.

Revision ID: d2a8f4c1b790
Revises: c4e2b7a91d60
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d2a8f4c1b790"
down_revision: Union[str, None] = "c4e2b7a91d60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "administrator_bootstrap_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("operator_identifier", sa.String(length=120), nullable=False),
        sa.Column("authorization_reference", sa.String(length=160), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("target_user_id", sa.UUID(), nullable=False),
        sa.Column("target_username", sa.String(length=100), nullable=False),
        sa.Column("assigned_role_codes", sa.ARRAY(sa.String(length=100)), server_default=sa.text("'{}'::varchar[]"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("length(trim(operator_identifier)) BETWEEN 1 AND 120", name="ck_admin_bootstrap_operator"),
        sa.CheckConstraint("length(trim(authorization_reference)) BETWEEN 1 AND 160", name="ck_admin_bootstrap_authorization"),
        sa.CheckConstraint("action IN ('bootstrap', 'provision', 'deactivate', 'credential_reset')", name="ck_admin_bootstrap_action"),
        sa.CheckConstraint("length(trim(target_username)) BETWEEN 1 AND 100", name="ck_admin_bootstrap_username"),
        sa.CheckConstraint("assigned_role_codes <@ ARRAY['inventory_administrator', 'security_administrator']::varchar[]", name="ck_admin_bootstrap_role_codes"),
        sa.ForeignKeyConstraint(["target_user_id"], ["public.users.id"], name="fk_admin_bootstrap_target_user", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_administrator_bootstrap_events"),
        schema="public",
    )
    op.create_index(
        "uq_administrator_bootstrap_once", "administrator_bootstrap_events", ["action"],
        unique=True, schema="public", postgresql_where=sa.text("action = 'bootstrap'"),
    )
    op.create_index(
        "ix_admin_bootstrap_target_occurred", "administrator_bootstrap_events",
        ["target_user_id", "occurred_at"], schema="public",
    )
    op.execute(
        """
        CREATE FUNCTION public.inventory_aios_prevent_administrator_bootstrap_audit_mutation()
        RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog
        AS $function$
        BEGIN
            RAISE EXCEPTION 'administrator_bootstrap_events is append-only'
                USING ERRCODE = '55000';
        END;
        $function$
        """
    )
    op.execute(
        "CREATE TRIGGER administrator_bootstrap_events_append_only "
        "BEFORE UPDATE OR DELETE ON public.administrator_bootstrap_events "
        "FOR EACH ROW EXECUTE FUNCTION public.inventory_aios_prevent_administrator_bootstrap_audit_mutation()"
    )
    op.execute(
        "CREATE TRIGGER administrator_bootstrap_events_no_truncate "
        "BEFORE TRUNCATE ON public.administrator_bootstrap_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION public.inventory_aios_prevent_administrator_bootstrap_audit_mutation()"
    )
    op.execute(
        "REVOKE ALL PRIVILEGES ON FUNCTION "
        "public.inventory_aios_prevent_administrator_bootstrap_audit_mutation() FROM PUBLIC"
    )


def downgrade() -> None:
    op.execute(
        "DO $block$ BEGIN IF EXISTS (SELECT 1 FROM public.administrator_bootstrap_events) "
        "THEN RAISE EXCEPTION 'cannot downgrade while bootstrap audit history exists'; END IF; END; $block$"
    )
    op.execute("DROP TRIGGER IF EXISTS administrator_bootstrap_events_no_truncate ON public.administrator_bootstrap_events")
    op.execute("DROP TRIGGER IF EXISTS administrator_bootstrap_events_append_only ON public.administrator_bootstrap_events")
    op.drop_index("ix_admin_bootstrap_target_occurred", table_name="administrator_bootstrap_events", schema="public")
    op.drop_index("uq_administrator_bootstrap_once", table_name="administrator_bootstrap_events", schema="public")
    op.drop_table("administrator_bootstrap_events", schema="public")
    op.execute("DROP FUNCTION public.inventory_aios_prevent_administrator_bootstrap_audit_mutation()")