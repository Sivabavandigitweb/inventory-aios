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

AUDIT_MIGRATION = Path(__file__).parents[1] / "alembic" / "versions" / "7d4a9c2e1b60_add_append_only_audit_events.py"


def test_audit_migration_is_append_only_and_refuses_history_loss_on_downgrade() -> None:
    migration = AUDIT_MIGRATION.read_text(encoding="utf-8")
    upgrade = migration.split("def downgrade()", maxsplit=1)[0]
    downgrade = migration.split("def downgrade()", maxsplit=1)[1]

    assert 'revision: str = "7d4a9c2e1b60"' in upgrade
    assert 'down_revision: Union[str, None] = "36368303c6c6"' in upgrade
    assert 'schema="public"' in upgrade
    assert '"public.users.id"' in upgrade
    assert "CREATE FUNCTION public.inventory_aios_audit_metadata_is_valid" in upgrade
    assert "CREATE FUNCTION public.inventory_aios_prevent_audit_event_mutation" in upgrade
    assert "public.inventory_aios_audit_metadata_is_valid(metadata)" in upgrade
    assert "CREATE TRIGGER audit_events_append_only" in upgrade
    assert "BEFORE UPDATE OR DELETE ON public.audit_events" in upgrade
    assert "BEFORE TRUNCATE ON public.audit_events" in upgrade
    assert "CREATE FUNCTION public." in upgrade
    assert "INSERT INTO" not in upgrade
    assert "DROP TRIGGER IF EXISTS audit_events_no_truncate ON public.audit_events" in downgrade
    assert "cannot downgrade while audit_events contains history" in downgrade
    assert 'op.drop_table("audit_events", schema="public")' in downgrade
    assert "DROP FUNCTION IF EXISTS public.inventory_aios_audit_metadata_is_valid(jsonb)" in downgrade


def test_audit_migration_database_metadata_validator_matches_application_contract() -> None:
    migration = AUDIT_MIGRATION.read_text(encoding="utf-8")
    validator = migration.split("CREATE FUNCTION public.inventory_aios_prevent", maxsplit=1)[0]

    assert "jsonb_typeof(input_value) IS DISTINCT FROM 'object'" in validator
    assert "('request_id', 'changed_fields', 'outcome')" in validator
    assert "jsonb_typeof(metadata_value) IS DISTINCT FROM 'string'" in validator
    assert "jsonb_array_elements(input_value -> 'changed_fields')" in validator
    assert "field_count > 20 OR field_name = ANY(seen_fields)" in validator
    assert "'success', 'failure'" in validator
