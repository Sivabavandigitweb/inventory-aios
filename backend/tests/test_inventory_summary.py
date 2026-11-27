from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes.inventory_summary import build_inventory_summary_router
from app.core.authentication import Principal
from app.core.errors import AppError
from app.core.permission_catalog import Capability
from app.services.inventory_summary import (
    AssetLifecycleSummary,
    Availability,
    DimensionSummary,
    InventorySummary,
    InventorySummaryService,
    QuantitySummary,
    SummaryMetric,
    SummaryScope,
)


def fixture_summary() -> InventorySummary:
    def metric(n: int) -> SummaryMetric:
        return SummaryMetric(status=Availability.AVAILABLE, value=n)

    return InventorySummary(
        individual_assets=AssetLifecycleSummary(
            available=metric(7), allocated=metric(4), repair=metric(1), damaged=metric(2), disposed=metric(0)
        ),
        by_category=[DimensionSummary(key="laptop", assets=metric(7))],
        by_location=[DimensionSummary(key="Colombo office", assets=metric(7))],
        quantity_inventory=[
            QuantitySummary(
                product_group="Mouse", location_group="Colombo office", unit="each",
                status=Availability.AVAILABLE, available_quantity=Decimal("12"),
            ),
            QuantitySummary(
                product_group="Cable", location_group="Colombo office", unit="box",
                status=Availability.AVAILABLE, available_quantity=Decimal("3"),
            ),
        ],
        availability=Availability.AVAILABLE,
        as_of=datetime(2026, 11, 27, tzinfo=UTC),
    )


class FakeScope:
    def __init__(self, scope):
        self.scope = scope
        self.seen = []

    def resolve(self, principal):
        self.seen.append(principal.user_id)
        return self.scope


class FakeSummaryProvider:
    def __init__(self, result=None):
        self.result = result or fixture_summary()
        self.scopes = []

    def read_summary(self, scope):
        self.scopes.append(scope)
        return self.result


def test_summary_requires_explicit_capability_and_approved_scope() -> None:
    scope = SummaryScope(department_ids=frozenset({uuid4()}))
    scopes = FakeScope(scope)
    provider = FakeSummaryProvider()
    service = InventorySummaryService(provider=provider, scopes=scopes)
    denied = Principal(uuid4(), frozenset())
    with pytest.raises(AppError) as error:
        service.get(denied)
    assert error.value.status_code == 403
    assert provider.scopes == []

    allowed = Principal(uuid4(), frozenset({Capability.SUMMARY_APPROVED_READ.value}))
    result = service.get(allowed)
    assert result is provider.result
    assert provider.scopes == [scope]


def test_empty_scope_and_provider_failure_fail_closed() -> None:
    with pytest.raises(ValueError):
        SummaryScope()
    principal = Principal(uuid4(), frozenset({Capability.SUMMARY_APPROVED_READ.value}))
    service = InventorySummaryService(provider=FakeSummaryProvider(), scopes=FakeScope(None))
    with pytest.raises(AppError) as denied:
        service.get(principal)
    assert denied.value.status_code == 403

    class FailedProvider:
        def read_summary(self, scope):
            raise RuntimeError("private provider detail")

    service = InventorySummaryService(
        provider=FailedProvider(), scopes=FakeScope(SummaryScope(organization_wide=True))
    )
    with pytest.raises(AppError) as unavailable:
        service.get(principal)
    assert unavailable.value.status_code == 503
    assert "private" not in str(unavailable.value)


def test_summary_schema_rejects_personal_detail_and_preserves_unit_groups() -> None:
    summary = fixture_summary()
    assert [line.unit for line in summary.quantity_inventory] == ["each", "box"]
    with pytest.raises(ValueError):
        DimensionSummary.model_validate(
            {"key": "laptop", "assets": {"status": "available", "value": 1}, "employee_name": "Private"}
        )
    with pytest.raises(ValueError):
        SummaryMetric(status=Availability.UNKNOWN, value=0)


def test_isolated_summary_router_requires_auth_dependency_and_is_not_in_operational_app() -> None:
    principal = Principal(uuid4(), frozenset({Capability.SUMMARY_APPROVED_READ.value}))
    service = InventorySummaryService(
        provider=FakeSummaryProvider(), scopes=FakeScope(SummaryScope(organization_wide=True))
    )
    isolated = FastAPI()
    isolated.include_router(
        build_inventory_summary_router(service=service, principal_dependency=lambda: principal),
        prefix="/api/v1",
    )
    assert TestClient(isolated).get("/api/v1/inventory-summary").status_code == 200

    from app.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/v1/inventory-summary" not in paths
