from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


class DatabaseConfigurationError(RuntimeError):
    """Raised when a database operation is requested without a configured URL."""


class DatabaseConnectionError(RuntimeError):
    """Raised when a configured database cannot be reached safely."""


def create_database_engine(settings: Settings | None = None) -> Engine:
    app_settings = settings or get_settings()
    if not app_settings.database_url:
        raise DatabaseConfigurationError(
            "INVENTORY_DATABASE_URL is not configured for this environment."
        )

    return create_engine(
        app_settings.database_url,
        pool_pre_ping=app_settings.database_pool_pre_ping,
        pool_size=app_settings.database_pool_size,
        max_overflow=app_settings.database_max_overflow,
        hide_parameters=True,
    )


@lru_cache
def get_engine() -> Engine:
    """Return the lazily-created application engine.

    Importing the application never opens a database connection. The first database
    operation creates the engine and SQLAlchemy opens connections on demand.
    """

    return create_database_engine()


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_db_session() -> Generator[Session, None, None]:
    """Yield a request-scoped session and always close it after use."""

    session = create_session_factory(get_engine())()
    try:
        yield session
    finally:
        session.close()


def check_database_connection(engine: Engine | None = None) -> None:
    """Execute a minimal read-only connection check without exposing credentials."""

    target_engine = engine or get_engine()
    try:
        with target_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise DatabaseConnectionError("Database connection check failed.") from exc