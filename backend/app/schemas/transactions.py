from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class AllocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    employee_id: UUID
    tracked_asset_id: UUID | None = None
    product_id: UUID | None = None
    location_id: UUID | None = None
    unit: Annotated[str, StringConstraints(min_length=1, max_length=30)] | None = None
    quantity: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)] = Decimal("1")

    @model_validator(mode="after")
    def target_is_unambiguous(self):
        individual = self.tracked_asset_id is not None
        quantity = all(value is not None for value in (self.product_id, self.location_id, self.unit))
        if individual == quantity:
            raise ValueError("Choose exactly one individual asset or quantity inventory target.")
        if individual and self.quantity != Decimal("1"):
            raise ValueError("An individual asset allocation has quantity one.")
        return self


class ReturnCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    allocation_line_id: UUID
    quantity: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
    condition: Annotated[str, StringConstraints(pattern="^(good|repair|damaged|unknown)$")]


class TransactionResult(BaseModel):
    id: UUID
    status: str
    replayed: bool = False


class AllocationRead(BaseModel):
    id: UUID
    employee_id: UUID
    status: str
    line_id: UUID
    tracked_asset_id: UUID | None
    product_id: UUID | None
    location_id: UUID | None
    unit: str | None
    quantity: Decimal
    returned_quantity: Decimal
    line_status: str
    created_at: datetime


class ReturnRead(BaseModel):
    id: UUID
    allocation_line_id: UUID
    quantity: Decimal
    condition: str
    status: str
    recorded_by_id: UUID
    created_at: datetime


class RepairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    issue_details: Annotated[str, StringConstraints(min_length=1, max_length=4000)]
    repair_provider: Annotated[str, StringConstraints(min_length=1, max_length=200)] | None = None


class RepairCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    condition: Annotated[str, StringConstraints(pattern="^(good|damaged)$")]
    notes: Annotated[str, StringConstraints(min_length=1, max_length=4000)] | None = None
    cost_amount: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)] | None = None
    cost_currency: Annotated[str, StringConstraints(pattern="^[A-Za-z]{3}$")] | None = None

    @model_validator(mode="after")
    def cost_pair(self):
        if (self.cost_amount is None) != (self.cost_currency is None):
            raise ValueError("Cost amount and currency must be supplied together.")
        return self


class DisposalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason_code: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    condition: Annotated[str, StringConstraints(pattern="^(good|repair|damaged|unknown)$")] | None = None


class QuantityDispositionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    quantity: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
    disposition: Annotated[str, StringConstraints(pattern="^(release|dispose)$")]
