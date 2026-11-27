from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Role(TimestampMixin, Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    user_roles: Mapped[list[UserRole]] = relationship(back_populates="role")

    __table_args__ = (UniqueConstraint("code", name="uq_roles_code"),)


class Department(TimestampMixin, Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    teams: Mapped[list[Team]] = relationship(back_populates="department")
    employees: Mapped[list[Employee]] = relationship(back_populates="department")

    __table_args__ = (UniqueConstraint("code", name="uq_departments_code"),)


class Team(TimestampMixin, Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    department: Mapped[Department] = relationship(back_populates="teams")
    employees: Mapped[list[Employee]] = relationship(back_populates="team")

    __table_args__ = (
        UniqueConstraint("department_id", "code", name="uq_teams_department_id_code"),
        Index("ix_teams_department_id_active", "department_id", "active"),
    )


class Designation(TimestampMixin, Base):
    __tablename__ = "designations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    employees: Mapped[list[Employee]] = relationship(back_populates="designation")

    __table_args__ = (UniqueConstraint("code", name="uq_designations_code"),)


class Employee(TimestampMixin, Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    employee_number: Mapped[str] = mapped_column(String(50), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT")
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT")
    )
    designation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("designations.id", ondelete="RESTRICT")
    )
    joining_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", server_default="active")
    exit_date: Mapped[date | None] = mapped_column(Date)

    department: Mapped[Department | None] = relationship(back_populates="employees")
    team: Mapped[Team | None] = relationship(back_populates="employees")
    designation: Mapped[Designation | None] = relationship(back_populates="employees")
    history: Mapped[list[EmployeeHistory]] = relationship(back_populates="employee")
    user: Mapped[User | None] = relationship(back_populates="employee", uselist=False)

    __table_args__ = (
        UniqueConstraint("employee_number", name="uq_employees_employee_number"),
        Index("ix_employees_department_team_status", "department_id", "team_id", "status"),
        Index("ix_employees_name", "last_name", "first_name"),
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", server_default="active")
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), unique=True
    )

    employee: Mapped[Employee | None] = relationship(back_populates="user")
    user_roles: Mapped[list[UserRole]] = relationship(back_populates="user")
    changed_history: Mapped[list[EmployeeHistory]] = relationship(back_populates="changed_by")

    __table_args__ = (
        Index("ix_users_username_lower", func.lower(username), unique=True),
        Index("ix_users_email_lower", func.lower(email), unique=True),
    )


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="user_roles")
    role: Mapped[Role] = relationship(back_populates="user_roles")


class EmployeeHistory(TimestampMixin, Base):
    __tablename__ = "employee_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    old_department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT")
    )
    new_department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id", ondelete="RESTRICT")
    )
    old_team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT")
    )
    new_team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.id", ondelete="RESTRICT")
    )
    old_designation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("designations.id", ondelete="RESTRICT")
    )
    new_designation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("designations.id", ondelete="RESTRICT")
    )
    change_type: Mapped[str] = mapped_column(String(40), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    change_source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user", server_default="user"
    )
    reason: Mapped[str | None] = mapped_column(Text)

    employee: Mapped[Employee] = relationship(back_populates="history")
    changed_by: Mapped[User | None] = relationship(back_populates="changed_history")

    __table_args__ = (
        Index("ix_employee_history_employee_effective", "employee_id", "effective_at"),
        CheckConstraint(
            "change_source IN ('user', 'system', 'import')",
            name="ck_employee_history_change_source",
        ),
        CheckConstraint(
            "change_source <> 'user' OR changed_by_id IS NOT NULL",
            name="ck_employee_history_user_actor",
        ),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    change_source: Mapped[str] = mapped_column(String(20), nullable=False)
    event_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB().with_variant(JSON(), "sqlite"), nullable=False,
        server_default=text("'{}'"),
    )
    previous_values: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True).with_variant(JSON(none_as_null=True), "sqlite")
    )
    updated_values: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True).with_variant(JSON(none_as_null=True), "sqlite")
    )

    __table_args__ = (
        CheckConstraint(
            "change_source IN ('user', 'system', 'import')",
            name="ck_audit_events_change_source",
        ),
        CheckConstraint(
            "change_source <> 'user' OR actor_user_id IS NOT NULL",
            name="ck_audit_events_user_actor",
        ),
        CheckConstraint("length(trim(action)) > 0", name="ck_audit_events_action_nonempty"),
        CheckConstraint("length(trim(entity_type)) > 0", name="ck_audit_events_entity_type_nonempty"),
        CheckConstraint(
            "public.inventory_aios_audit_metadata_is_valid(metadata)",
            name="ck_audit_events_metadata_valid",
        ),
        CheckConstraint("previous_values IS NULL OR public.inventory_aios_audit_values_are_valid(previous_values)",
                        name="ck_audit_events_previous_values_object"),
        CheckConstraint("updated_values IS NULL OR public.inventory_aios_audit_values_are_valid(updated_values)",
                        name="ck_audit_events_updated_values_object"),
        Index("ix_audit_events_actor_occurred", "actor_user_id", "occurred_at"),
        Index("ix_audit_events_entity_occurred", "entity_type", "entity_id", "occurred_at"),
        {"schema": "public"},
    )


class AdministratorBootstrapEvent(Base):
    """Dedicated operator-attributed, append-only administrator lifecycle audit."""

    __tablename__ = "administrator_bootstrap_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    operator_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    authorization_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    target_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    target_username: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_role_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String(100)), nullable=False, server_default=text("'{}'::varchar[]")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("length(trim(operator_identifier)) BETWEEN 1 AND 120", name="ck_admin_bootstrap_operator"),
        CheckConstraint("length(trim(authorization_reference)) BETWEEN 1 AND 160", name="ck_admin_bootstrap_authorization"),
        CheckConstraint("action IN ('bootstrap', 'provision', 'deactivate', 'credential_reset')", name="ck_admin_bootstrap_action"),
        CheckConstraint("length(trim(target_username)) BETWEEN 1 AND 100", name="ck_admin_bootstrap_username"),
        CheckConstraint(
            "assigned_role_codes <@ ARRAY['inventory_administrator', 'security_administrator']::varchar[]",
            name="ck_admin_bootstrap_role_codes",
        ),
        Index("uq_administrator_bootstrap_once", "action", unique=True,
              postgresql_where=text("action = 'bootstrap'")),
        Index("ix_admin_bootstrap_target_occurred", "target_user_id", "occurred_at"),
        {"schema": "public"},
    )

class AssetCategory(TimestampMixin, Base):
    __tablename__ = "asset_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    tracking_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    __table_args__ = (
        UniqueConstraint("code", name="uq_asset_categories_code"),
        CheckConstraint(
            "tracking_mode IN ('individual', 'quantity')",
            name="ck_asset_categories_tracking_mode",
        ),
    )


class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    __table_args__ = (Index("ix_suppliers_name", "name"),)


class Location(TimestampMixin, Base):
    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    parent_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT")
    )
    location_type: Mapped[str | None] = mapped_column(String(50))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    parent: Mapped[Location | None] = relationship(
        remote_side="Location.id", back_populates="children"
    )
    children: Mapped[list[Location]] = relationship(back_populates="parent")

    __table_args__ = (
        UniqueConstraint("code", name="uq_locations_code"),
        Index("ix_locations_parent_active", "parent_location_id", "active"),
    )
