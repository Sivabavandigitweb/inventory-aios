from pathlib import Path

MIGRATION = Path(__file__).parents[1] / "alembic" / "versions" / "36368303c6c6_create_core_foundation_tables.py"


def test_initial_migration_contains_database_safeguards_without_upgrade_execution() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    upgrade = migration.split("def downgrade()", maxsplit=1)[0]

    assert "server_default=sa.text('gen_random_uuid()')" in upgrade
    assert "CREATE OR REPLACE FUNCTION inventory_aios_set_updated_at()" in upgrade
    assert "CREATE TRIGGER employee_history_append_only" in upgrade
    assert "BEFORE UPDATE OR DELETE ON employee_history" in upgrade
    assert "ck_employee_history_change_source" in upgrade
    assert "ck_employee_history_user_actor" in upgrade
    assert "op.drop_table" not in upgrade
    assert "DROP TRIGGER" not in upgrade
    assert "DROP FUNCTION" not in upgrade


def test_initial_migration_downgrade_removes_safeguard_objects() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    downgrade = migration.split("def downgrade()", maxsplit=1)[1]

    assert "DROP TRIGGER IF EXISTS employee_history_append_only" in downgrade
    assert "DROP FUNCTION IF EXISTS inventory_aios_set_updated_at()" in downgrade
    assert "DROP FUNCTION IF EXISTS inventory_aios_prevent_employee_history_mutation()" in downgrade