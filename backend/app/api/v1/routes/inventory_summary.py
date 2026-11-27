"""Isolated, dependency-injected summary adapter; not registered in api.router."""

from typing import Annotated, Callable

from fastapi import APIRouter, Depends

from app.core.authentication import Principal
from app.core.errors import AppError
from app.services.inventory_summary import InventorySummary, InventorySummaryService


def build_inventory_summary_router(
    *,
    principal_dependency: Callable[..., Principal],
    service: InventorySummaryService | None = None,
    service_dependency: Callable[..., InventorySummaryService] | None = None,
) -> APIRouter:
    """Build a protected summary route with a static or request-scoped service."""
    if (service is None) == (service_dependency is None):
        raise ValueError("Supply exactly one summary service or service dependency.")

    def fixed_service() -> InventorySummaryService:
        assert service is not None
        return service

    resolve_service = service_dependency or fixed_service

    router = APIRouter(prefix="/inventory-summary", tags=["inventory-summary-preview"])

    @router.get("", response_model=InventorySummary)
    def read_summary(
        principal: Annotated[Principal, Depends(principal_dependency)],
        resolved_service: Annotated[InventorySummaryService, Depends(resolve_service)],
    ) -> InventorySummary:
        try:
            return resolved_service.get(principal)
        except AppError:
            raise

    return router
