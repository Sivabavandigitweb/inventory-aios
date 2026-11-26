"""add local password credential and opaque session storage

Revision ID: 0ea2d9c71b45
Revises: 7d4a9c2e1b60
Create Date: 2026-11-26
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0ea2d9c71b45"
down_revision: Union[str, None] = "7d4a9c2e1b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_password_credentials",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "password_changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "credential_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "credential_version > 0",
            name="ck_user_password_credentials_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["public.users.id"],
            name="fk_user_password_credentials_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_password_credentials"),
        schema="public",
    )
    op.execute(
        """
        CREATE TRIGGER user_password_credentials_set_updated_at
        BEFORE UPDATE ON public.user_password_credentials
        FOR EACH ROW
        EXECUTE FUNCTION public.inventory_aios_set_updated_at()
        """
    )

    op.create_table(
        "auth_sessions",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name="ck_auth_sessions_token_hash_length"
        ),
        sa.CheckConstraint(
            "credential_version > 0", name="ck_auth_sessions_credential_version_positive"
        ),
        sa.CheckConstraint(
            "last_seen_at >= created_at", name="ck_auth_sessions_last_seen_after_creation"
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name="ck_auth_sessions_expiry_after_creation"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["public.users.id"],
            name="fk_auth_sessions_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
        schema="public",
    )
    op.create_index(
        "ix_auth_sessions_user_revoked",
        "auth_sessions",
        ["user_id", "revoked_at"],
        schema="public",
    )
    op.create_index(
        "ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"], schema="public"
    )


def downgrade() -> None:
    # Preserve credentials and session/revocation evidence; require explicit recovery first.
    op.execute(
        """
        DO $block$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.user_password_credentials LIMIT 1)
               OR EXISTS (SELECT 1 FROM public.auth_sessions LIMIT 1) THEN
                RAISE EXCEPTION
                    'cannot downgrade while authentication credentials or sessions exist';
            END IF;
        END;
        $block$
        """
    )
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions", schema="public")
    op.drop_index("ix_auth_sessions_user_revoked", table_name="auth_sessions", schema="public")
    op.drop_table("auth_sessions", schema="public")
    op.execute(
        "DROP TRIGGER IF EXISTS user_password_credentials_set_updated_at "
        "ON public.user_password_credentials"
    )
    op.drop_table("user_password_credentials", schema="public")
