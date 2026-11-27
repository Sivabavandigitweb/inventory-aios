import subprocess
import sys
from pathlib import Path

MIGRATION = Path(__file__).parents[1] / "alembic" / "versions" / "c4e2b7a91d60_add_shared_login_attempt_buckets.py"


def test_shared_login_attempt_migration_is_additive_and_privilege_neutral() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    upgrade, downgrade = source.split("def downgrade()", maxsplit=1)
    assert 'revision: str = "c4e2b7a91d60"' in source
    assert 'down_revision: Union[str, None] = "b2d4f6a8c013"' in source
    assert '"auth_login_attempt_buckets"' in upgrade
    assert "key_digest" in upgrade and "octet_length(key_digest) = 32" in upgrade
    assert "SECURITY DEFINER" in upgrade
    assert "LIMIT GREATEST(1, LEAST(COALESCE(requested_batch, 100), 100))" in upgrade
    assert "REVOKE ALL PRIVILEGES ON FUNCTION" in upgrade
    assert "GRANT " not in upgrade
    assert "INSERT INTO" not in upgrade
    assert "cannot downgrade populated login attempt protection state" in downgrade


def test_shared_login_attempt_migration_compiles_offline_to_postgresql() -> None:
    backend_dir = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head", "--sql"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE public.auth_login_attempt_buckets" in result.stdout
    assert "inventory_aios_cleanup_login_attempts(" in result.stdout
    assert "retention_seconds integer DEFAULT 86400" in result.stdout
    assert "GRANT " not in result.stdout
    assert "INVENTORY_MIGRATION_DATABASE_URL" not in result.stderr
