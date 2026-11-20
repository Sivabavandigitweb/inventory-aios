from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
    check_database_connection,
    create_database_engine,
    create_session_factory,
)
from app.main import create_app

settings = Settings(environment="test", database_url=None)
client = TestClient(create_app(settings))


def test_database_settings_are_environment_driven() -> None:
    default_settings = Settings(_env_file=None)
    configured = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://inventory_aios:local-only@localhost:5432/inventory_aios_dev",
    )

    assert default_settings.database_url is None
    assert configured.database_url is not None
    assert configured.database_pool_pre_ping is True


def test_engine_requires_explicit_database_url() -> None:
    try:
        create_database_engine(Settings(_env_file=None, database_url=None))
    except DatabaseConfigurationError as exc:
        assert "INVENTORY_DATABASE_URL" in str(exc)
    else:
        raise AssertionError("Expected missing database configuration to fail safely")


def test_session_factory_uses_safe_session_defaults() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    factory = create_session_factory(engine)
    session = factory()

    assert isinstance(session, Session)
    assert session.autoflush is False
    assert session.expire_on_commit is False
    session.close()
    engine.dispose()


def test_connection_errors_are_safe_and_do_not_expose_connection_details() -> None:
    class BrokenEngine:
        def connect(self):
            raise OperationalError("SELECT 1", {}, RuntimeError("connection refused"))

    try:
        check_database_connection(BrokenEngine())  # type: ignore[arg-type]
    except DatabaseConnectionError as exc:
        assert str(exc) == "Database connection check failed."
        assert "connection refused" not in str(exc)
    else:
        raise AssertionError("Expected connection failure to be wrapped")


def test_database_health_is_separate_and_safe_when_unconfigured(monkeypatch) -> None:
    def raise_database_not_configured() -> None:
        raise DatabaseConfigurationError("Database URL is not configured.")

    monkeypatch.setattr(
        "app.api.v1.routes.database.check_database_connection",
        raise_database_not_configured,
    )
    response = client.get("/api/v1/health/database")

    assert response.status_code == 503
    assert response.json() == {"status": "not_configured", "database": "postgresql"}