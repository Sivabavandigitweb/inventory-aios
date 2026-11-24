"""add append-only audit events

Revision ID: 7d4a9c2e1b60
Revises: 36368303c6c6
Create Date: 2026-11-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7d4a9c2e1b60"
down_revision: Union[str, None] = "36368303c6c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION public.inventory_aios_audit_metadata_is_valid(input_value jsonb)
        RETURNS boolean
        LANGUAGE plpgsql
        IMMUTABLE
        SET search_path = pg_catalog
        AS $function$
        DECLARE
            metadata_key text;
            metadata_value jsonb;
            field_value jsonb;
            field_name text;
            field_count integer := 0;
            seen_fields text[] := ARRAY[]::text[];
        BEGIN
            IF input_value IS NULL
               OR pg_catalog.jsonb_typeof(input_value) IS DISTINCT FROM 'object' THEN
                RETURN FALSE;
            END IF;

            FOR metadata_key IN
                SELECT pg_catalog.jsonb_object_keys(input_value)
            LOOP
                IF metadata_key NOT IN ('request_id', 'changed_fields', 'outcome') THEN
                    RETURN FALSE;
                END IF;
            END LOOP;

            IF input_value ? 'request_id' THEN
                metadata_value := input_value -> 'request_id';
                IF pg_catalog.jsonb_typeof(metadata_value) IS DISTINCT FROM 'string'
                   OR (input_value ->> 'request_id') !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
                    RETURN FALSE;
                END IF;
            END IF;

            IF input_value ? 'changed_fields' THEN
                IF pg_catalog.jsonb_typeof(input_value -> 'changed_fields') IS DISTINCT FROM 'array' THEN
                    RETURN FALSE;
                END IF;
                FOR field_value IN
                    SELECT item.value
                    FROM pg_catalog.jsonb_array_elements(input_value -> 'changed_fields') AS item(value)
                LOOP
                    IF pg_catalog.jsonb_typeof(field_value) IS DISTINCT FROM 'string' THEN
                        RETURN FALSE;
                    END IF;
                    field_name := field_value #>> ARRAY[]::text[];
                    IF field_name !~ '^[a-z][a-z0-9_]{0,63}$'
                       OR field_name ~ '(password|token|secret|credential|authorization)' THEN
                        RETURN FALSE;
                    END IF;
                    field_count := field_count + 1;
                    IF field_count > 20 OR field_name = ANY(seen_fields) THEN
                        RETURN FALSE;
                    END IF;
                    seen_fields := pg_catalog.array_append(seen_fields, field_name);
                END LOOP;
            END IF;

            IF input_value ? 'outcome' THEN
                IF pg_catalog.jsonb_typeof(input_value -> 'outcome') IS DISTINCT FROM 'string'
                   OR input_value ->> 'outcome' NOT IN ('success', 'failure') THEN
                    RETURN FALSE;
                END IF;
            END IF;

            RETURN TRUE;
        END;
        $function$
        """
    )
    op.create_table(
        "audit_events",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("change_source", sa.String(length=20), nullable=False),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"), nullable=False,
        ),
        sa.CheckConstraint(
            "change_source IN ('user', 'system', 'import')",
            name="ck_audit_events_change_source",
        ),
        sa.CheckConstraint(
            "change_source <> 'user' OR actor_user_id IS NOT NULL",
            name="ck_audit_events_user_actor",
        ),
        sa.CheckConstraint("length(trim(action)) > 0", name="ck_audit_events_action_nonempty"),
        sa.CheckConstraint(
            "length(trim(entity_type)) > 0", name="ck_audit_events_entity_type_nonempty"
        ),
        sa.CheckConstraint(
            "public.inventory_aios_audit_metadata_is_valid(metadata)",
            name="ck_audit_events_metadata_valid",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["public.users.id"],
            name="fk_audit_events_actor_user_id_users", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
        schema="public",
    )
    op.create_index(
        "ix_audit_events_actor_occurred",
        "audit_events",
        ["actor_user_id", "occurred_at"],
        schema="public",
    )
    op.create_index(
        "ix_audit_events_entity_occurred",
        "audit_events",
        ["entity_type", "entity_id", "occurred_at"],
        schema="public",
    )
    op.execute(
        """
        CREATE FUNCTION public.inventory_aios_prevent_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only; write a compensating event'
                USING ERRCODE = '55000';
        END;
        $function$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON public.audit_events
        FOR EACH ROW EXECUTE FUNCTION public.inventory_aios_prevent_audit_event_mutation()
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_no_truncate
        BEFORE TRUNCATE ON public.audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION public.inventory_aios_prevent_audit_event_mutation()
        """
    )


def downgrade() -> None:
    # Do not silently discard audit history during a downgrade.
    op.execute(
        """
        DO $block$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.audit_events LIMIT 1) THEN
                RAISE EXCEPTION 'cannot downgrade while audit_events contains history';
            END IF;
        END;
        $block$
        """
    )
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_truncate ON public.audit_events")
    op.execute("DROP TRIGGER IF EXISTS audit_events_append_only ON public.audit_events")
    op.drop_index(
        "ix_audit_events_entity_occurred", table_name="audit_events", schema="public"
    )
    op.drop_index(
        "ix_audit_events_actor_occurred", table_name="audit_events", schema="public"
    )
    op.drop_table("audit_events", schema="public")
    op.execute(
        "DROP FUNCTION IF EXISTS public.inventory_aios_prevent_audit_event_mutation()"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS public.inventory_aios_audit_metadata_is_valid(jsonb)"
    )
