from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class EmployeeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employee_number: Identifier
    first_name: Name
    last_name: Name
    department_id: UUID
    team_id: UUID
    designation_id: UUID
    joining_date: date


class EmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    employee_number: str
    first_name: str
    last_name: str
    department_id: UUID | None
    team_id: UUID | None
    designation_id: UUID | None
    joining_date: date | None
    status: str


class EmployeePage(BaseModel):
    items: list[EmployeeRead]
    total: int
    limit: int
    offset: int


class EmployeeSyncStatus(BaseModel):
    configured: bool
    last_success_at: datetime | None


class EmployeeFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    q: str | None = Field(default=None, min_length=1, max_length=100)
    department_id: UUID | None = None
    team_id: UUID | None = None
    designation_id: UUID | None = None
    status: str | None = Field(default=None, min_length=1, max_length=30)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=10000)
