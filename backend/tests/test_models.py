from sqlalchemy.dialects.postgresql import UUID

from app.models import Base

EXPECTED_TABLES = {
    "asset_categories",
    "departments",
    "designations",
    "employee_history",
    "employees",
    "locations",
    "roles",
    "suppliers",
    "teams",
    "user_roles",
    "users",
}


def test_core_metadata_contains_only_approved_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_uuid_primary_keys_are_used_for_core_entities() -> None:
    for table_name in EXPECTED_TABLES - {"user_roles"}:
        primary_key = next(iter(Base.metadata.tables[table_name].primary_key.columns))
        assert isinstance(primary_key.type, UUID)


def test_employee_history_preserves_organizational_changes() -> None:
    table = Base.metadata.tables["employee_history"]

    assert {
        "old_department_id",
        "new_department_id",
        "old_team_id",
        "new_team_id",
        "old_designation_id",
        "new_designation_id",
        "change_type",
        "effective_at",
        "changed_by_id",
    }.issubset(table.c.keys())
    assert {foreign_key.target_fullname for column in table.columns for foreign_key in column.foreign_keys} >= {
        "employees.id",
        "users.id",
        "departments.id",
        "teams.id",
        "designations.id",
    }


def test_reference_data_and_identity_constraints_exist() -> None:
    assert {"code"}.issubset(Base.metadata.tables["roles"].c.keys())
    assert {"code"}.issubset(Base.metadata.tables["departments"].c.keys())
    assert {"code"}.issubset(Base.metadata.tables["designations"].c.keys())
    assert {"code"}.issubset(Base.metadata.tables["asset_categories"].c.keys())
    assert {"code"}.issubset(Base.metadata.tables["locations"].c.keys())
    assert "employee_number" in Base.metadata.tables["employees"].c
    assert "employee_id" in Base.metadata.tables["users"].c


def test_asset_category_tracking_mode_is_constrained() -> None:
    constraints = Base.metadata.tables["asset_categories"].constraints
    assert any(
        constraint.name == "ck_asset_categories_tracking_mode"
        for constraint in constraints
    )


def test_timestamps_are_non_nullable_on_core_tables() -> None:
    for table_name, table in Base.metadata.tables.items():
        if table_name == "user_roles":
            continue
        assert table.c.created_at.nullable is False
        assert table.c.updated_at.nullable is False

def test_uuid_primary_keys_have_application_and_postgresql_defaults() -> None:
    for table_name in EXPECTED_TABLES - {"user_roles"}:
        column = next(iter(Base.metadata.tables[table_name].primary_key.columns))
        assert column.default is not None
        assert column.server_default is not None
        assert str(column.server_default.arg) == "gen_random_uuid()"


def test_history_requires_actor_for_user_source_and_allows_explicit_sources() -> None:
    table = Base.metadata.tables["employee_history"]
    constraints = {constraint.name for constraint in table.constraints}

    assert "ck_employee_history_change_source" in constraints
    assert "ck_employee_history_user_actor" in constraints
    assert table.c.changed_by_id.nullable is True
    assert table.c.change_source.server_default is not None


def test_timestamp_columns_have_orm_update_support() -> None:
    for table_name, table in Base.metadata.tables.items():
        if table_name == "user_roles":
            continue
        assert table.c.updated_at.onupdate is not None