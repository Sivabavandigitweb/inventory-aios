from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.errors import AppError
from app.models import Base, WorkflowApproval
from app.services.audit import AuditEventInput, AuditEventValidationError, build_audit_event
from app.services.inventory_summary import (
    Availability,
    SQLAlchemyInventorySummaryProvider,
    SummaryScope,
)
from app.services.workflows import transition_asset, validate_asset_transition


def test_workflow_models_are_registered_with_expected_guards() -> None:
    expected = {
        "public.allocations", "public.allocation_lines", "public.inventory_returns",
        "public.asset_repairs", "public.disposal_requests", "public.employee_exit_clearances",
        "public.workflow_approvals", "public.inventory_notifications",
    }
    assert expected <= set(Base.metadata.tables)
    line = Base.metadata.tables["public.allocation_lines"]
    assert any(index.name == "uq_allocation_lines_active_asset" and index.unique for index in line.indexes)
    assert any(constraint.name == "ck_allocation_lines_tracking_target" for constraint in line.constraints)
    assert any(constraint.name == "ck_disposal_requests_target"
               for constraint in Base.metadata.tables["public.disposal_requests"].constraints)
    assert WorkflowApproval.__table__.c.decided_by_id.nullable


@pytest.mark.parametrize(
    ("source", "target"),
    [("available", "allocated"), ("disposed", "available"), ("repair", "allocated"),
     ("unknown", "available"), ("allocated", "disposed")],
)
def test_invalid_asset_lifecycle_edges_are_rejected(source: str, target: str) -> None:
    with pytest.raises(AppError) as error:
        validate_asset_transition(source, target)
    assert error.value.status_code == 409


@pytest.mark.parametrize(
    ("source", "target"),
    [("available", "repair"), ("available", "damaged"), ("repair", "available"),
     ("damaged", "disposed")],
)
def test_approved_asset_lifecycle_edges_are_recognized(source: str, target: str) -> None:
    validate_asset_transition(source, target)


def test_asset_transition_has_no_implicit_authorization_or_database_access() -> None:
    session = MagicMock()
    with pytest.raises(AppError) as error:
        transition_asset(session, asset_id=uuid4(), actor_user_id=uuid4(), target="repair", policy=None)
    assert error.value.status_code == 503
    session.execute.assert_not_called()


def test_audit_values_accept_allowlisted_non_sensitive_fields() -> None:
    event = build_audit_event(AuditEventInput(
        actor_user_id=uuid4(), action="asset.lifecycle_updated", entity_type="tracked_asset",
        entity_id=uuid4(), previous_values={"lifecycle_status": "available"},
        updated_values={"lifecycle_status": "repair"},
    ))
    assert event.previous_values == {"lifecycle_status": "available"}
    assert event.updated_values == {"lifecycle_status": "repair"}


@pytest.mark.parametrize("field", ["employee_name", "serial_number", "purchase_cost", "password_hash", "token"])
def test_audit_value_contract_rejects_sensitive_or_unapproved_fields(field: str) -> None:
    with pytest.raises(AuditEventValidationError):
        build_audit_event(AuditEventInput(
            actor_user_id=uuid4(), action="asset.lifecycle_updated", entity_type="tracked_asset",
            entity_id=uuid4(), updated_values={field: "synthetic-value"},
        ))


def test_summary_provider_returns_only_approved_aggregate_schema_and_suppresses_small_groups() -> None:
    session = MagicMock()
    aggregate_rows = [
        [("available", 4), ("repair", 1)],
        [("Laptop", 4), ("Phone", 1)],
        [("Main location", 4), ("Small office", 1)],
        [("Laptop", "Main location", "each", Decimal("3.000"))],
    ]
    session.execute.side_effect = [MagicMock(all=MagicMock(return_value=rows)) for rows in aggregate_rows]
    stamp = datetime(2026, 11, 26, tzinfo=timezone.utc)
    session.scalar.side_effect = [stamp, stamp]
    exposure = MagicMock(allow_individual_aggregates=MagicMock(return_value=True),
                         allow_quantity_aggregates=MagicMock(return_value=True))
    provider = SQLAlchemyInventorySummaryProvider(session=session, minimum_group_size=2,
                                                   exposure_policy=exposure)
    result = provider.read_summary(SummaryScope(organization_wide=True))
    assert result.individual_assets.available.value == 4
    assert [row.key for row in result.by_category] == ["Laptop"]
    assert [row.key for row in result.by_location] == ["Main location"]
    assert result.quantity_inventory[0].available_quantity == Decimal("3.000")
    assert result.as_of == stamp
    assert result.availability is Availability.AVAILABLE
    assert not {"employee_name", "serial_number", "purchase_cost", "repair_notes"} & set(type(result).model_fields)


def test_summary_provider_requires_suppression_threshold_and_known_scope() -> None:
    with pytest.raises(ValueError):
        SQLAlchemyInventorySummaryProvider(session=MagicMock(), minimum_group_size=None,
                                           exposure_policy=MagicMock())
    with pytest.raises(ValueError):
        SQLAlchemyInventorySummaryProvider(session=MagicMock(), minimum_group_size=2,
                                           exposure_policy=None)
    provider = SQLAlchemyInventorySummaryProvider(session=MagicMock(), minimum_group_size=2,
                                                   exposure_policy=MagicMock())
    with pytest.raises(AppError):
        provider.read_summary(SummaryScope(department_ids=frozenset({uuid4()})))
