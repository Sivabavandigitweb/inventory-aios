import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import MigrationSettings
from app.core.migration_security import require_migration_url, verify_migration_identity


def test_missing_migration_configuration_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="INVENTORY_MIGRATION_DATABASE_URL"):
        require_migration_url(None)


def test_migration_configuration_never_falls_back_to_runtime_url(monkeypatch) -> None:
    monkeypatch.setenv(
        "INVENTORY_DATABASE_URL",
        "postgresql+psycopg://inventory_aios_app:runtime-secret@localhost/runtime",
    )
    monkeypatch.delenv("INVENTORY_MIGRATION_DATABASE_URL", raising=False)
    settings = MigrationSettings(_env_file=None)
    assert settings.migration_database_url is None
    with pytest.raises(RuntimeError, match="INVENTORY_MIGRATION_DATABASE_URL"):
        require_migration_url(settings.migration_database_url)


def test_migration_url_requires_migrator_login_without_echoing_url() -> None:
    url = "postgresql+psycopg://runtime-secret@localhost:5432/inventory_aios_restore_check"
    with pytest.raises(RuntimeError, match="authenticate as inventory_aios_migrator") as error:
        require_migration_url(url)
    assert "runtime-secret" not in str(error.value)


def test_failed_owner_role_assumption_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="did not assume"):
        verify_migration_identity("inventory_aios_migrator", "inventory_aios_migrator")


def test_incorrect_session_identity_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="unexpected session"):
        verify_migration_identity("other_login", "inventory_aios_owner")


def test_successful_owner_role_verification() -> None:
    verify_migration_identity("inventory_aios_migrator", "inventory_aios_owner")


def test_unexpected_integration_database_is_rejected() -> None:
    from app.core.integration_test_config import require_isolated_test_url

    for url in (
        "postgresql://inventory_aios_app@localhost:5432/inventory_aios_dev",
        "postgresql://inventory_aios_app@example.com:5432/inventory_aios_restore_check",
        "postgresql://other_user@localhost:5432/inventory_aios_restore_check",
    ):
        with pytest.raises(RuntimeError, match="Integration tests require"):
            require_isolated_test_url(url)


def test_approved_restore_database_is_accepted_without_connecting() -> None:
    from app.core.integration_test_config import require_isolated_test_url

    url = "postgresql+psycopg://inventory_aios_app:placeholder@localhost:5432/inventory_aios_restore_check"
    assert require_isolated_test_url(url) == url


def test_offline_migration_sql_generation_needs_no_database_credentials() -> None:
    backend_dir = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head", "--sql"],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE departments" in result.stdout
    assert "INVENTORY_MIGRATION_DATABASE_URL" not in result.stderr


def test_migration_url_is_restricted_to_local_restore_rehearsal() -> None:
    for url in (
        "postgresql+psycopg://inventory_aios_migrator@localhost:5432/inventory_aios_dev",
        "postgresql+psycopg://inventory_aios_migrator@db.example:5432/inventory_aios_restore_check",
    ):
        with pytest.raises(RuntimeError, match="restricted to localhost:5432"):
            require_migration_url(url)


def test_approved_rehearsal_migration_url_is_accepted() -> None:
    url = "postgresql+psycopg://inventory_aios_migrator@localhost:5432/inventory_aios_restore_check"
    assert require_migration_url(url) == url
