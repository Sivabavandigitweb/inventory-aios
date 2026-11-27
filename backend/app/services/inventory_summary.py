"""Restricted aggregate inventory summary contract; no operational provider is wired."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.authentication import Principal
from app.core.errors import AppError
from app.core.permission_catalog import Capability
from app.models import AssetCategory, InventoryBalance, InventoryProduct, Location, TrackedAsset


class Availability(StrEnum):
    AVAILABLE = "available"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class SummaryMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Availability
    value: int | None

    @model_validator(mode="after")
    def value_matches_status(self):
        if self.status is Availability.AVAILABLE:
            if type(self.value) is not int or self.value < 0:
                raise ValueError("Available metrics require a non-negative integer.")
        elif self.value is not None:
            raise ValueError("Unavailable or unknown metrics must not contain a value.")
        return self


class AssetLifecycleSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    available: SummaryMetric
    allocated: SummaryMetric
    repair: SummaryMetric
    damaged: SummaryMetric
    disposed: SummaryMetric


class DimensionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    key: str = Field(min_length=1, max_length=120)
    assets: SummaryMetric


class QuantitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    product_group: str = Field(min_length=1, max_length=120)
    location_group: str = Field(min_length=1, max_length=120)
    unit: str = Field(min_length=1, max_length=32)
    status: Availability
    available_quantity: Decimal | None

    @model_validator(mode="after")
    def quantity_matches_status(self):
        if self.status is Availability.AVAILABLE:
            if self.available_quantity is None or self.available_quantity < 0:
                raise ValueError("Available quantity requires a non-negative value.")
        elif self.available_quantity is not None:
            raise ValueError("Unknown quantity must not be represented as a number.")
        return self


class InventorySummary(BaseModel):
    """Allowlisted response; operational rows and personal/serial fields are impossible."""

    model_config = ConfigDict(extra="forbid", strict=True)

    individual_assets: AssetLifecycleSummary
    by_category: list[DimensionSummary]
    by_location: list[DimensionSummary]
    quantity_inventory: list[QuantitySummary]
    availability: Availability
    as_of: datetime | None


@dataclass(frozen=True, slots=True)
class SummaryScope:
    """Server-derived scope. Empty scope is not interpreted as organization-wide."""

    organization_wide: bool = False
    department_ids: frozenset[UUID] = frozenset()
    location_ids: frozenset[UUID] = frozenset()

    def __post_init__(self) -> None:
        if type(self.organization_wide) is not bool:
            raise ValueError("Summary scope must be explicit.")
        if not self.organization_wide and not (self.department_ids or self.location_ids):
            raise ValueError("An empty summary scope is not authorized.")
        if any(not isinstance(item, UUID) for item in self.department_ids | self.location_ids):
            raise ValueError("Summary scope identifiers must be UUIDs.")


class SummaryScopePolicy(Protocol):
    def resolve(self, principal: Principal) -> SummaryScope | None: ...


class InventorySummaryProvider(Protocol):
    def read_summary(self, scope: SummaryScope) -> InventorySummary: ...


class SummaryExposurePolicy(Protocol):
    def allow_individual_aggregates(self, scope: SummaryScope) -> bool: ...
    def allow_quantity_aggregates(self, scope: SummaryScope) -> bool: ...


class InventorySummaryService:
    def __init__(self, *, provider: InventorySummaryProvider, scopes: SummaryScopePolicy) -> None:
        self._provider = provider
        self._scopes = scopes

    def get(self, principal: Principal) -> InventorySummary:
        if not isinstance(principal, Principal):
            raise AppError("FORBIDDEN", "This operation is not permitted.", 403)
        if Capability.SUMMARY_APPROVED_READ.value not in principal.permissions:
            raise AppError("FORBIDDEN", "This operation is not permitted.", 403)
        try:
            scope = self._scopes.resolve(principal)
            if not isinstance(scope, SummaryScope):
                raise AppError("FORBIDDEN", "This operation is not permitted.", 403)
            response = self._provider.read_summary(scope)
            if not isinstance(response, InventorySummary):
                raise ValueError("Provider response does not match the summary schema.")
            return response
        except AppError:
            raise
        except Exception:
            raise AppError(
                "SUMMARY_UNAVAILABLE", "Inventory summary is temporarily unavailable.", 503
            ) from None


class SQLAlchemyInventorySummaryProvider:
    """Aggregate-only provider; organizational scope and privacy threshold are mandatory."""

    def __init__(self, *, session: Session, minimum_group_size: int | None,
                 exposure_policy: SummaryExposurePolicy | None) -> None:
        if type(minimum_group_size) is not int or minimum_group_size < 1:
            raise ValueError("A configured aggregate suppression threshold must be supplied.")
        if exposure_policy is None:
            raise ValueError("An explicit approved summary exposure policy must be supplied.")
        self._session = session
        self._minimum_group_size = minimum_group_size
        self._exposure_policy = exposure_policy

    def read_summary(self, scope: SummaryScope) -> InventorySummary:
        if scope.department_ids:
            # The current asset schema has no validated department-to-location authorization map.
            raise AppError("SUMMARY_UNAVAILABLE", "Approved summary scope is unavailable.", 503)
        try:
            include_individual = self._exposure_policy.allow_individual_aggregates(scope)
            include_quantity = self._exposure_policy.allow_quantity_aggregates(scope)
            if type(include_individual) is not bool or type(include_quantity) is not bool:
                raise AppError("SUMMARY_UNAVAILABLE", "Approved summary exposure is unavailable.", 503)
            asset_clauses = []
            balance_clauses = []
            if not scope.organization_wide:
                if not scope.location_ids:
                    raise AppError("FORBIDDEN", "This operation is not permitted.", 403)
                asset_clauses.append(TrackedAsset.location_id.in_(scope.location_ids))
                balance_clauses.append(InventoryBalance.location_id.in_(scope.location_ids))

            lifecycle_rows = self._session.execute(select(
                TrackedAsset.lifecycle_status, func.count(TrackedAsset.id)
            ).where(*asset_clauses).group_by(TrackedAsset.lifecycle_status)).all() if include_individual else []
            lifecycle_counts = {status: int(count) for status, count in lifecycle_rows}
            lifecycle = AssetLifecycleSummary(**{
                key: SummaryMetric(status=Availability.AVAILABLE, value=lifecycle_counts.get(key, 0))
                for key in ("available", "allocated", "repair", "damaged", "disposed")
            })

            category_rows = self._session.execute(select(
                AssetCategory.name, func.count(TrackedAsset.id)
            ).select_from(AssetCategory).join(
                InventoryProduct, InventoryProduct.category_id == AssetCategory.id
            ).join(TrackedAsset, TrackedAsset.product_id == InventoryProduct.id)
             .where(*asset_clauses).group_by(AssetCategory.name).order_by(AssetCategory.name)).all() if include_individual else []
            location_rows = self._session.execute(select(
                Location.name, func.count(TrackedAsset.id)
            ).join(TrackedAsset, TrackedAsset.location_id == Location.id)
             .where(*asset_clauses).group_by(Location.name).order_by(Location.name)).all() if include_individual else []
            by_category = [DimensionSummary(key=name, assets=SummaryMetric(status=Availability.AVAILABLE, value=int(count)))
                           for name, count in category_rows if int(count) >= self._minimum_group_size]
            by_location = [DimensionSummary(key=name, assets=SummaryMetric(status=Availability.AVAILABLE, value=int(count)))
                           for name, count in location_rows if int(count) >= self._minimum_group_size]

            quantity_rows = self._session.execute(select(
                InventoryProduct.name, Location.name, InventoryBalance.unit,
                func.sum(InventoryBalance.on_hand - InventoryBalance.reserved - InventoryBalance.quarantined),
            ).join(InventoryProduct, InventoryProduct.id == InventoryBalance.product_id)
             .join(Location, Location.id == InventoryBalance.location_id)
             .where(*balance_clauses).group_by(InventoryProduct.name, Location.name, InventoryBalance.unit)
             .order_by(InventoryProduct.name, Location.name, InventoryBalance.unit)).all() if include_quantity else []
            quantity = [QuantitySummary(product_group=product, location_group=location, unit=unit,
                         status=Availability.AVAILABLE, available_quantity=Decimal(amount))
                        for product, location, unit, amount in quantity_rows]
            asset_as_of = self._session.scalar(select(func.max(TrackedAsset.updated_at)).where(*asset_clauses)) if include_individual else None
            quantity_as_of = self._session.scalar(select(func.max(InventoryBalance.updated_at)).where(*balance_clauses)) if include_quantity else None
            as_of = max((value for value in (asset_as_of, quantity_as_of) if value is not None), default=None)
            return InventorySummary(
                individual_assets=lifecycle, by_category=by_category, by_location=by_location,
                quantity_inventory=quantity, availability=Availability.AVAILABLE, as_of=as_of,
            )
        except AppError:
            raise
        except SQLAlchemyError:
            raise AppError("SUMMARY_UNAVAILABLE", "Inventory summary is temporarily unavailable.", 503) from None
        except Exception:
            raise AppError("SUMMARY_UNAVAILABLE", "Inventory summary is temporarily unavailable.", 503) from None
