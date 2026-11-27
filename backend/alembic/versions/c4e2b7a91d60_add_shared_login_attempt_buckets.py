"""Add bounded privacy-preserving shared login attempt buckets.

Revision ID: c4e2b7a91d60
Revises: b2d4f6a8c013
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e2b7a91d60"
down_revision: Union[str, None] = "b2d4f6a8c013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_login_attempt_buckets",
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("key_digest", sa.LargeBinary(length=32), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failures", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("in_flight", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("scope IN ('account', 'source')", name="ck_auth_login_attempt_scope"),
        sa.CheckConstraint("octet_length(key_digest) = 32", name="ck_auth_login_attempt_digest_length"),
        sa.CheckConstraint("failures >= 0 AND in_flight >= 0", name="ck_auth_login_attempt_counts_nonnegative"),
        sa.PrimaryKeyConstraint("scope", "key_digest", name="pk_auth_login_attempt_buckets"),
        schema="public",
    )
    op.create_index(
        "ix_auth_login_attempt_updated_at",
        "auth_login_attempt_buckets",
        ["updated_at"],
        schema="public",
    )
    op.execute(
        """
        CREATE FUNCTION public.inventory_aios_cleanup_login_attempts(
            requested_batch integer DEFAULT 100,
            retention_seconds integer DEFAULT 86400
        )
        RETURNS integer
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $function$
        DECLARE removed_count integer;
        BEGIN
            WITH stale AS (
                SELECT scope, key_digest
                FROM public.auth_login_attempt_buckets
                WHERE updated_at < pg_catalog.clock_timestamp()
                    - make_interval(secs => GREATEST(900, LEAST(COALESCE(retention_seconds, 86400), 604800)))
                  AND in_flight = 0
                  AND (blocked_until IS NULL OR blocked_until <= pg_catalog.clock_timestamp())
                ORDER BY updated_at
                FOR UPDATE SKIP LOCKED
                LIMIT GREATEST(1, LEAST(COALESCE(requested_batch, 100), 100))
            )
            DELETE FROM public.auth_login_attempt_buckets AS bucket
            USING stale
            WHERE bucket.scope = stale.scope AND bucket.key_digest = stale.key_digest;
            GET DIAGNOSTICS removed_count = ROW_COUNT;
            RETURN removed_count;
        END;
        $function$
        """
    )
    op.execute("REVOKE ALL PRIVILEGES ON FUNCTION public.inventory_aios_cleanup_login_attempts(integer, integer) FROM PUBLIC")


def downgrade() -> None:
    op.execute(
        "DO $block$ BEGIN IF EXISTS (SELECT 1 FROM public.auth_login_attempt_buckets) "
        "THEN RAISE EXCEPTION 'cannot downgrade populated login attempt protection state'; END IF; END; $block$"
    )
    op.execute("DROP FUNCTION public.inventory_aios_cleanup_login_attempts(integer, integer)")
    op.drop_index("ix_auth_login_attempt_updated_at", table_name="auth_login_attempt_buckets", schema="public")
    op.drop_table("auth_login_attempt_buckets", schema="public")
