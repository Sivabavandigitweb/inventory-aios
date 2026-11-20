import logging

from fastapi import APIRouter, Response, status

from app.db.health import DatabaseHealthResponse
from app.db.session import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
    check_database_connection,
)

logger = logging.getLogger("inventory_aios.database")
router = APIRouter(tags=["database"])


@router.get(
    "/health/database",
    response_model=DatabaseHealthResponse,
    summary="Check database connectivity",
)
def database_health(response: Response) -> DatabaseHealthResponse:
    try:
        check_database_connection()
    except DatabaseConfigurationError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return DatabaseHealthResponse(status="not_configured")
    except DatabaseConnectionError:
        logger.warning("database_health_check_failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return DatabaseHealthResponse(status="unavailable")
    return DatabaseHealthResponse(status="healthy")