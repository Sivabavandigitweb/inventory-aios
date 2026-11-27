"""Opt-in disposable PostgreSQL checks; never run against development or production."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_integration_test_settings
from app.core.integration_test_config import require_owner_test_url

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def inventory_owner_engine():
    settings = get_integration_test_settings()
    try:
        url = require_owner_test_url(settings.owner_database_url)
    except RuntimeError as exc:
        if settings.owner_database_url is None:
            pytest.skip("INVENTORY_TEST_OWNER_DATABASE_URL is not configured.")
        pytest.fail(str(exc))
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
            identity = connection.execute(text(
                "SELECT current_database(), session_user, current_user, inet_server_port(), "
                "(SELECT version_num FROM public.alembic_version)"
            )).one()
    if identity != ("inventory_aios_restore_check", "inventory_aios_migrator",
                    "inventory_aios_owner", 5432, "d2a8f4c1b790"):
        engine.dispose()
        pytest.fail("Inventory integration target identity or revision was rejected.")
    yield engine
    engine.dispose()


def _seed_product(engine):
    category_id, location_id, product_id = uuid4(), uuid4(), uuid4()
    suffix = uuid4().hex
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
        connection.execute(text("INSERT INTO public.asset_categories (id, code, name, tracking_mode) "
                                "VALUES (:id, :code, 'TEST category', 'quantity')"),
                           {"id": category_id, "code": f"TEST-{suffix}"})
        connection.execute(text("INSERT INTO public.locations (id, code, name) "
                                "VALUES (:id, :code, 'TEST location')"),
                           {"id": location_id, "code": f"TEST-{suffix}"})
        connection.execute(text("INSERT INTO public.inventory_products (id, category_id, name) "
                                "VALUES (:id, :category, 'TEST product')"),
                           {"id": product_id, "category": category_id})
    return category_id, location_id, product_id, suffix


def _cleanup(engine, values):
    category_id, location_id, product_id, _ = values
    with engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
        connection.execute(text("DELETE FROM public.inventory_balances WHERE product_id=:id"), {"id": product_id})
        connection.execute(text("DELETE FROM public.inventory_products WHERE id=:id"), {"id": product_id})
        connection.execute(text("DELETE FROM public.locations WHERE id=:id"), {"id": location_id})
        connection.execute(text("DELETE FROM public.asset_categories WHERE id=:id"), {"id": category_id})


def test_negative_balance_rejection_rolls_back_the_whole_transaction(inventory_owner_engine):
    ids = _seed_product(inventory_owner_engine)
    category_id, location_id, product_id, _ = ids
    with pytest.raises(IntegrityError):
        with inventory_owner_engine.begin() as connection:
            connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
            connection.execute(text("INSERT INTO public.inventory_balances "
                "(product_id, location_id, unit, on_hand, reserved) "
                "VALUES (:product, :location, 'each', -1, 0)"),
                {"product": product_id, "location": location_id})
            connection.execute(text("UPDATE public.inventory_products SET name='TEST changed' WHERE id=:id"),
                               {"id": product_id})
    try:
        with inventory_owner_engine.begin() as connection:
            connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
            assert connection.execute(text("SELECT name FROM public.inventory_products WHERE id=:id"),
                                      {"id": product_id}).scalar_one() == "TEST product"
            assert connection.execute(text("SELECT count(*) FROM public.inventory_balances WHERE product_id=:id"),
                                      {"id": product_id}).scalar_one() == 0
    finally:
        _cleanup(inventory_owner_engine, ids)


def test_concurrent_same_balance_key_cannot_create_duplicate_balances(inventory_owner_engine):
    ids = _seed_product(inventory_owner_engine)
    _, location_id, product_id, _ = ids
    barrier = Barrier(2)

    def insert_balance():
        try:
            with inventory_owner_engine.begin() as connection:
                connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
                barrier.wait(timeout=10)
                connection.execute(text("INSERT INTO public.inventory_balances "
                    "(product_id, location_id, unit, on_hand, reserved) "
                    "VALUES (:product, :location, 'each', 1, 0)"),
                    {"product": product_id, "location": location_id})
            return "inserted"
        except IntegrityError:
            return "conflict"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: insert_balance(), range(2)))
        assert sorted(results) == ["conflict", "inserted"]
        with inventory_owner_engine.begin() as connection:
            connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
            assert connection.execute(text("SELECT count(*) FROM public.inventory_balances "
                "WHERE product_id=:product AND location_id=:location AND unit='each'"),
                {"product": product_id, "location": location_id}).scalar_one() == 1
    finally:
        _cleanup(inventory_owner_engine, ids)
