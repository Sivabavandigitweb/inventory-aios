from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

settings = Settings(environment="test")
client = TestClient(create_app(settings))


def test_application_startup() -> None:
    app = create_app(settings)

    assert app.title == "Inventory AIOS API"
    assert app.version == settings.app_version


def test_health_endpoint_returns_application_health() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "Inventory AIOS API",
        "environment": "test",
        "version": "0.1.0",
    }
    assert response.headers["X-Request-ID"]


def test_api_route_is_versioned() -> None:
    assert client.get("/health").status_code == 404
    assert client.get("/api/v1/health").status_code == 200


def test_cors_allows_local_frontend_origin() -> None:
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_unknown_route_uses_structured_error_handler() -> None:
    response = client.get("/api/v1/not-a-real-route", headers={"X-Request-ID": "test-request"})

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "test-request"
    assert response.json() == {
        "error": {"code": "HTTP_ERROR", "message": "Not Found"},
        "request_id": "test-request",
    }