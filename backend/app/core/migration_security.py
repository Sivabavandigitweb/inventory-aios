"""Fail-closed validation for online Alembic connection identity."""

from sqlalchemy.engine import make_url

MIGRATOR_ROLE = "inventory_aios_migrator"
OWNER_ROLE = "inventory_aios_owner"


def require_migration_url(database_url: str | None) -> str:
    if not database_url:
        raise RuntimeError("INVENTORY_MIGRATION_DATABASE_URL is required for online migrations.")
    try:
        url = make_url(database_url)
    except (ValueError, TypeError):
        raise RuntimeError("The migration database URL is invalid.") from None
    if url.username != MIGRATOR_ROLE:
        raise RuntimeError("The migration connection must authenticate as inventory_aios_migrator.")
    if (
        url.database != "inventory_aios_restore_check"
        or url.host not in {"localhost", "127.0.0.1", "::1"}
        or url.port != 5432
    ):
        raise RuntimeError(
            "Rehearsal migrations are restricted to localhost:5432/"
            "inventory_aios_restore_check."
        )
    return database_url


def verify_migration_identity(session_user: str, current_user: str) -> None:
    if session_user != MIGRATOR_ROLE:
        raise RuntimeError("The migration connection has an unexpected session identity.")
    if current_user != OWNER_ROLE:
        raise RuntimeError("The migration connection did not assume the required owner role.")
