"""Metadata and compilation checks only; these do not prove PostgreSQL enforcement."""

import pytest
from sqlalchemy import CheckConstraint, DateTime, UniqueConstraint, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateIndex, CreateTable

from app.models import AssetCategory, Base, InventoryProduct, Location, Receipt, User


@pytest.fixture(autouse=True)
def prohibit_database_connections(monkeypatch):
    import psycopg
    from sqlalchemy.engine import Engine

    def forbidden(*args, **kwargs):
        raise AssertionError("Asset model tests must remain offline")

    monkeypatch.setattr(psycopg, "connect", forbidden)
    monkeypatch.setattr(Engine, "connect", forbidden)


@pytest.mark.parametrize("model", [InventoryProduct, Receipt])
def test_model_registered_with_public_schema_and_uuid_defaults(model):
    table = model.__table__
    assert Base.metadata.tables[f"public.{table.name}"] is table
    assert table.schema == "public"
    assert list(table.primary_key.columns.keys()) == ["id"]
    assert table.primary_key.name == f"pk_{table.name}"
    assert isinstance(table.c.id.type, UUID)
    assert table.c.id.default is not None
    assert str(table.c.id.server_default.arg) == "gen_random_uuid()"
    for name in ("created_at", "updated_at"):
        column = table.c[name]
        assert isinstance(column.type, DateTime) and column.type.timezone
        assert not column.nullable and column.server_default is not None
    assert table.c.updated_at.onupdate is not None


@pytest.mark.parametrize(("model", "column_name", "target"), [
    (InventoryProduct, "category_id", AssetCategory),
    (Receipt, "received_by_id", User),
    (Receipt, "location_id", Location),
])
def test_foreign_keys_reuse_existing_master_tables_with_restrict(model, column_name, target):
    column = model.__table__.c[column_name]
    foreign_key, = column.foreign_keys
    assert foreign_key.column is target.__table__.c.id
    assert foreign_key.ondelete == "RESTRICT"
    assert not column.nullable
    assert foreign_key.constraint.name == (
        f"fk_{model.__tablename__}_{column_name}_{target.__tablename__}"
    )
    assert any(list(index.columns)[0] is column for index in model.__table__.indexes)


def test_catalog_contract_does_not_decide_units_or_sku_uniqueness():
    table = InventoryProduct.__table__
    assert set(table.c.keys()) == {
        "id", "category_id", "sku", "name", "brand", "model", "specifications",
        "active", "created_at", "updated_at",
    }
    assert table.c.name.type.length == 200 and not table.c.name.nullable
    assert table.c.sku.type.length == 80 and table.c.sku.nullable
    assert table.c.brand.nullable and table.c.model.nullable
    assert isinstance(table.c.specifications.type, JSONB)
    assert not table.c.specifications.nullable
    assert str(table.c.specifications.server_default.arg) == "'{}'::jsonb"
    assert str(table.c.active.server_default.arg) == "true"
    assert not any(isinstance(c, UniqueConstraint) for c in table.constraints)
    assert not any(index.unique for index in table.indexes)
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert checks == {
        "ck_inventory_products_name_nonempty": "length(trim(name)) > 0",
        "ck_inventory_products_sku_nonempty": "sku IS NULL OR length(trim(sku)) > 0",
        "ck_inventory_products_specifications_object": "jsonb_typeof(specifications) = 'object'",
    }


def test_receipt_records_explicit_arrival_without_approval_or_number_defaults():
    table = Receipt.__table__
    assert set(table.c.keys()) == {
        "id", "received_at", "received_by_id", "location_id", "external_reference",
        "notes", "created_at", "updated_at",
    }
    assert table.c.received_at.type.timezone and not table.c.received_at.nullable
    assert table.c.received_at.default is None and table.c.received_at.server_default is None
    assert table.c.external_reference.nullable and table.c.notes.nullable
    assert not any(isinstance(c, UniqueConstraint) for c in table.constraints)
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert checks == {"ck_receipts_external_reference_nonempty":
                      "external_reference IS NULL OR length(trim(external_reference)) > 0"}
    assert {index.name: tuple(index.columns.keys()) for index in table.indexes} == {
        "ix_receipts_received_at": ("received_at",),
        "ix_receipts_received_by_id": ("received_by_id",),
        "ix_receipts_location_received_at": ("location_id", "received_at"),
    }


def test_relationships_configure_without_duplicate_masters_or_delete_cascades():
    configure_mappers()
    for model, name, target in (
        (InventoryProduct, "category", AssetCategory),
        (Receipt, "received_by", User),
        (Receipt, "location", Location),
    ):
        relationship = inspect(model).relationships[name]
        assert relationship.mapper.class_ is target
        assert not relationship.uselist
        assert "delete" not in relationship.cascade
        assert "delete-orphan" not in relationship.cascade
    category = AssetCategory(code="CAT", name="Catalog", tracking_mode="individual")
    product = InventoryProduct(name="Catalog entry", category=category)
    assert product.category is category
    location = Location(code="LOC", name="Location")
    receiver = User(username="test", email="test@example.invalid", display_name="Test")
    receipt = Receipt(location=location, received_by=receiver)
    assert receipt.location is location and receipt.received_by is receiver
    assert "public.asset_categories" not in Base.metadata.tables
    assert "public.users" not in Base.metadata.tables
    assert "public.locations" not in Base.metadata.tables


@pytest.mark.parametrize("model", [InventoryProduct, Receipt])
def test_postgresql_ddl_and_indexes_compile_without_connections(model):
    table = model.__table__
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert f"CREATE TABLE public.{table.name}" in ddl
    assert "UUID DEFAULT gen_random_uuid() NOT NULL" in ddl
    assert "TIMESTAMP WITH TIME ZONE" in ddl
    assert "ON DELETE RESTRICT" in ddl
    for index in table.indexes:
        sql = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
        assert index.name in sql and f"ON public.{table.name}" in sql
    # Legacy masters have schema=None in metadata; the migration must explicitly target public.
    qualified = str(CreateTable(table).compile(
        dialect=postgresql.dialect(), schema_translate_map={None: "public"},
        render_schema_translate=True,
    ))
    for fk in table.foreign_keys:
        assert f"REFERENCES public.{fk.column.table.name} (id)" in qualified


def test_all_existing_and_new_metadata_compile_together():
    for table in Base.metadata.sorted_tables:
        assert str(CreateTable(table).compile(dialect=postgresql.dialect()))
    for name in ("assets", "receipt_lines", "inventory_lots", "inventory_balances",
                 "inventory_movements", "asset_registration_events"):
        assert name not in Base.metadata.tables
        assert f"public.{name}" not in Base.metadata.tables
