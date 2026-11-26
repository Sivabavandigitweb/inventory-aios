import subprocess
import sys
from pathlib import Path

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0ea2d9c71b45_add_authentication_credentials_and_sessions.py"
)


def test_additive_authentication_migration_has_expected_dependency_and_objects() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    upgrade, downgrade = source.split("def downgrade()", maxsplit=1)

    assert 'revision: str = "0ea2d9c71b45"' in source
    assert 'down_revision: Union[str, None] = "7d4a9c2e1b60"' in source
    assert '"user_password_credentials"' in upgrade
    assert '"auth_sessions"' in upgrade
    assert '"public.users.id"' in upgrade
    assert "ck_user_password_credentials_version_positive" in upgrade
    assert "ck_auth_sessions_token_hash_length" in upgrade
    assert "ck_auth_sessions_credential_version_positive" in upgrade
    assert "ck_auth_sessions_last_seen_after_creation" in upgrade
    assert "ck_auth_sessions_expiry_after_creation" in upgrade
    assert "ix_auth_sessions_user_revoked" in upgrade
    assert "ix_auth_sessions_expires_at" in upgrade
    assert "INSERT INTO" not in upgrade
    assert "GRANT " not in upgrade
    assert "password_hash" not in upgrade.split('"auth_sessions"', maxsplit=1)[1]
    assert "cannot downgrade while authentication credentials or sessions exist" in downgrade
    assert 'op.drop_table("auth_sessions", schema="public")' in downgrade
    assert 'op.drop_table("user_password_credentials", schema="public")' in downgrade


def test_authentication_migration_compiles_to_postgresql_without_database_access() -> None:
    backend_dir = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head", "--sql"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE public.user_password_credentials" in result.stdout
    assert "CREATE TABLE public.auth_sessions" in result.stdout
    assert "REFERENCES public.users (id) ON DELETE RESTRICT" in result.stdout
    assert "CREATE TRIGGER user_password_credentials_set_updated_at" in result.stdout
    assert "GRANT " not in result.stdout
    assert "INSERT INTO public.users" not in result.stdout
    assert "INVENTORY_MIGRATION_DATABASE_URL" not in result.stderr

    downgrade = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "downgrade",
            "0ea2d9c71b45:7d4a9c2e1b60",
            "--sql",
        ],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert downgrade.returncode == 0, downgrade.stderr
    assert "cannot downgrade while authentication credentials or sessions exist" in downgrade.stdout
    assert "DROP TABLE public.auth_sessions" in downgrade.stdout
    assert "DROP TABLE public.user_password_credentials" in downgrade.stdout
