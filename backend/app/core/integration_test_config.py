"""Strict target validation for PostgreSQL integration-test connections."""

from sqlalchemy.engine import make_url


def require_isolated_test_url(database_url: str | None) -> str:
    if not database_url:
        raise RuntimeError("INVENTORY_TEST_DATABASE_URL is required for PostgreSQL integration tests.")
    try:
        url = make_url(database_url)
    except (ValueError, TypeError):
        raise RuntimeError("The integration test database URL is invalid.") from None
    if (
        url.database != "inventory_aios_restore_check"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.port != 5432
        or url.username != "inventory_aios_app"
    ):
        raise RuntimeError(
            "Integration tests require inventory_aios_app on localhost:5432/"
            "inventory_aios_restore_check."
        )
    return database_url


def require_owner_test_url(database_url: str | None) -> str:
    if not database_url:
        raise RuntimeError("INVENTORY_TEST_OWNER_DATABASE_URL is required for owner-level trigger tests.")
    try:
        url = make_url(database_url)
    except (ValueError, TypeError):
        raise RuntimeError("The owner-level test database URL is invalid.") from None
    if (
        url.database != "inventory_aios_restore_check"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.port != 5432
        or url.username != "inventory_aios_migrator"
    ):
        raise RuntimeError(
            "Owner-level tests require inventory_aios_migrator on localhost:5432/"
            "inventory_aios_restore_check."
        )
    return database_url
