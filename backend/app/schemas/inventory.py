import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

TextFilter = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    category_id: UUID
    category_name: str
    sku: str | None
    name: str
    brand: str | None
    model: str | None
    specifications: dict[str, object]
    active: bool


class MasterDataRead(BaseModel):
    id: UUID
    code: str
    name: str


class CategoryRead(MasterDataRead):
    tracking_mode: str


class RegistrationCandidateRead(BaseModel):
    id: UUID
    receipt_id: UUID
    product_id: UUID
    product_name: str
    location_name: str
    tracking_mode: str
    quantity: Decimal
    unit: str
    remaining_quantity: Decimal


class RegistrationApprovalRead(BaseModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    required_capability: str
    requested_by_id: UUID
    created_at: datetime


class RegistrationFinalizationRead(BaseModel):
    request_id: UUID
    tracking_mode: str
    product_name: str
    quantity: Decimal
    unit: str


class ProductPage(BaseModel):
    items: list[ProductRead]
    total: int
    limit: int
    offset: int


class AssetRead(BaseModel):
    id: UUID
    asset_number: str | None
    product_id: UUID
    category_id: UUID
    category_name: str
    product_name: str
    brand: str | None
    model: str | None
    location_id: UUID
    location_name: str
    lifecycle_status: str
    condition: str | None


class AssetPage(BaseModel):
    items: list[AssetRead]
    total: int
    limit: int
    offset: int


class QuantityBalanceRead(BaseModel):
    product_id: UUID
    product_name: str
    location_id: UUID
    location_name: str
    unit: str
    on_hand: Decimal
    reserved: Decimal
    quarantined: Decimal
    available: Decimal
    updated_at: datetime


class ReceiptRead(BaseModel):
    id: UUID
    received_at: datetime
    received_by_id: UUID
    location_id: UUID
    location_name: str
    supplier_id: UUID | None
    external_reference: str | None


class ReceiptPage(BaseModel):
    items: list[ReceiptRead]
    total: int
    limit: int
    offset: int


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category_id: UUID
    sku: Annotated[str, StringConstraints(min_length=1, max_length=80)] | None = None
    name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    brand: Annotated[str, StringConstraints(min_length=1, max_length=150)] | None = None
    model: Annotated[str, StringConstraints(min_length=1, max_length=150)] | None = None
    specifications: dict[str, object] = Field(default_factory=dict)

    @field_validator("specifications")
    @classmethod
    def validate_specifications(cls, value: dict[str, object]) -> dict[str, object]:
        if len(value) > 40 or len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 8192:
            raise ValueError("Specifications exceed the supported size.")
        blocked = ("password", "token", "secret", "credential", "authorization", "employee")
        pending: list[tuple[object, int]] = [(value, 0)]
        nodes = 0
        while pending:
            current, depth = pending.pop()
            nodes += 1
            if nodes > 500 or depth > 8:
                raise ValueError("Specifications exceed the supported structure.")
            if isinstance(current, dict):
                for key, nested in current.items():
                    if not isinstance(key, str) or any(term in key.casefold() for term in blocked):
                        raise ValueError("Specifications contain a restricted field.")
                    pending.append((nested, depth + 1))
            elif isinstance(current, list):
                pending.extend((nested, depth + 1) for nested in current)
        return value


class ReceiptLineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    product_id: UUID
    quantity: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
    unit: Annotated[str, StringConstraints(min_length=1, max_length=30)]
    tracking_mode: Annotated[str, StringConstraints(pattern="^(individual|quantity)$")]


class ReceiptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    received_at: datetime
    location_id: UUID
    supplier_id: UUID | None = None
    external_reference: Annotated[str, StringConstraints(min_length=1, max_length=150)] | None = None
    lines: list[ReceiptLineCreate] = Field(min_length=1, max_length=100)


class AssetRegistrationSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    receipt_line_id: UUID
    asset_number: Annotated[str, StringConstraints(min_length=1, max_length=100)] | None = None
    serial_number: Annotated[str, StringConstraints(min_length=1, max_length=150)] | None = None
    condition: Annotated[str, StringConstraints(min_length=1, max_length=40)] | None = None


class QuantityRegistrationSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    receipt_line_id: UUID
    quantity: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=3)]
    unit: Annotated[str, StringConstraints(min_length=1, max_length=30)]


class WorkflowApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    decision: Annotated[str, StringConstraints(pattern="^(approved|rejected)$")]
    reason_code: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{0,39}$")] | None = None


class WriteResult(BaseModel):
    id: UUID
    status: str
    replayed: bool = False


class PageQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: TextFilter | None = None
    category_id: UUID | None = None
    location_id: UUID | None = None
    lifecycle_status: Annotated[str, StringConstraints(pattern="^(available|allocated|repair|damaged|disposed)$")] | None = None
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)
