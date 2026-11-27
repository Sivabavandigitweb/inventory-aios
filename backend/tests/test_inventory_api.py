from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.authentication import authenticated_principal
from app.db.session import get_db_session
from app.main import app


def test_inventory_reads_reject_unauthenticated_requests_before_queries():
    session = MagicMock()
    app.dependency_overrides[get_db_session] = lambda: session
    try:
        with TestClient(app) as client:
            for path in ("/api/v1/inventory/products", "/api/v1/inventory/assets",
                         "/api/v1/inventory/assets/00000000-0000-4000-8000-000000000001",
                         "/api/v1/inventory/quantity-balances", "/api/v1/inventory/receipts"):
                response = client.get(path)
                assert response.status_code == 401
        session.execute.assert_not_called()
        session.scalars.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_inventory_capability_is_required_even_for_authenticated_principal():
    from app.core.authorization import Principal

    session = MagicMock()
    app.dependency_overrides[get_db_session] = lambda: session
    app.dependency_overrides[authenticated_principal] = lambda: Principal(
        user_id=uuid4(), permissions=frozenset())
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/inventory/assets")
        assert response.status_code == 403
        session.execute.assert_not_called()
    finally:
        app.dependency_overrides.clear()
