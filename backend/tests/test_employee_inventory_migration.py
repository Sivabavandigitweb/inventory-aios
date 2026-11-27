import subprocess
import sys
from pathlib import Path

MIGRATION = (Path(__file__).parents[1] / "alembic" / "versions"
             / "4b6f10a2c903_add_employee_sync_and_inventory_foundation.py")


def test_additive_migration_has_expected_dependency_and_no_seed_or_privilege_changes():
    source = MIGRATION.read_text(encoding="utf-8")
    upgrade, downgrade = source.split("def downgrade()", maxsplit=1)
    assert 'revision: str = "4b6f10a2c903"' in source
    assert 'down_revision: Union[str, None] = "0ea2d9c71b45"' in source
    for table in ("idempotency_requests", "inventory_products", "receipts", "receipt_lines", "tracked_assets",
                  "quantity_inventory_lots", "inventory_balances", "inventory_movements",
                  "employee_source_identities", "employee_sync_runs"):
        assert f'op.create_table("{table}"' in upgrade
    assert "REFERENCES" not in upgrade  # Foreign keys are represented as Alembic constraints.
    assert "GRANT " not in upgrade
    assert "INSERT INTO" not in upgrade
    assert "cannot downgrade populated employee-sync or inventory tables" in downgrade


def test_employee_inventory_migration_compiles_offline_to_postgresql():
    backend_dir = Path(__file__).parents[1]
    result = subprocess.run([sys.executable, "-m", "alembic", "-c", "alembic.ini",
                             "upgrade", "head", "--sql"], cwd=backend_dir,
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    for table in ("inventory_products", "tracked_assets", "inventory_balances",
                  "inventory_movements", "employee_source_identities", "employee_sync_runs"):
        assert f"CREATE TABLE public.{table}" in result.stdout
    assert "REFERENCES public.employees (id) ON DELETE RESTRICT" in result.stdout
    assert "CREATE TABLE public.asset_registration_requests" in result.stdout
    assert "CREATE TABLE public.quantity_registration_requests" in result.stdout
    assert "inventory_aios_audit_values_are_valid" in result.stdout
    assert "GRANT " not in result.stdout


def test_registration_migration_is_additive_and_chained_after_workflow_contracts():
    path = (Path(__file__).parents[1] / "alembic" / "versions"
            / "a1c7e3052b94_registration_requests_and_audit_validation.py")
    source = path.read_text(encoding="utf-8")
    upgrade, downgrade = source.split("def downgrade()", maxsplit=1)
    assert 'revision: str = "a1c7e3052b94"' in source
    assert 'down_revision: Union[str, None] = "9c81e247a610"' in source
    assert "GRANT " not in upgrade
    assert "INSERT INTO" not in upgrade
    assert "cannot downgrade populated registration requests or audit values" in downgrade
