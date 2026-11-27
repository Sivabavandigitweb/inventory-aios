from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.errors import AppError
from app.schemas.transactions import AllocationCreate, ReturnCreate
from app.services.inventory_transactions import (
    decide_allocation,
    decide_return,
    issue_allocation,
    record_return,
    request_allocation,
)
from app.services.inventory_writes import _fingerprint


class Policy:
    def __init__(self, permitted=True):
        self.permitted = permitted

    def authorize(self, **_):
        return self.permitted

    def requires_approval(self, **_):
        return True

    def approval_satisfied(self, **_):
        return True


class Result:
    def __init__(self, scalar=None, rows=None, first=None):
        self.scalar = scalar
        self.rows = rows or []
        self.first_row = first

    def scalar_one_or_none(self):
        return self.scalar

    def scalar_one(self):
        return self.scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: self.rows)

    def first(self):
        return self.first_row


class Session:
    def __init__(self, results):
        self.results = iter(results)
        self.added = []
        self.flushes = 0

    @contextmanager
    def begin_nested(self):
        yield

    def execute(self, _statement):
        return next(self.results)

    def scalar(self, _statement):
        return 0

    def add(self, value):
        self.added.append(value)

    def flush(self):
        self.flushes += 1


def test_allocation_contract_requires_exactly_one_target():
    with pytest.raises(ValidationError):
        AllocationCreate(employee_id=uuid4())
    with pytest.raises(ValidationError):
        AllocationCreate(employee_id=uuid4(), tracked_asset_id=uuid4(),
                         product_id=uuid4(), location_id=uuid4(), unit="each")
    with pytest.raises(ValidationError):
        AllocationCreate(employee_id=uuid4(), tracked_asset_id=uuid4(), quantity="2")


def test_quantity_allocation_contract_preserves_compatible_unit_target():
    command = AllocationCreate(employee_id=uuid4(), product_id=uuid4(), location_id=uuid4(),
                               unit="box", quantity="1.250")
    assert command.quantity == 1.250


@pytest.mark.parametrize("operation", ["allocation", "return"])
def test_matching_idempotency_replay_precedes_current_stock_or_custody_checks(operation):
    actor, resource_id = uuid4(), uuid4()
    if operation == "allocation":
        command = AllocationCreate(employee_id=uuid4(), tracked_asset_id=uuid4())
        payload = command.model_dump(mode="json")
    else:
        command = ReturnCreate(allocation_line_id=uuid4(), quantity="1", condition="good")
        payload = command.model_dump(mode="json")
    existing = SimpleNamespace(request_fingerprint=_fingerprint(payload), status="succeeded",
                               resource_id=resource_id, resource_type="pending_approval")
    session = Session([Result(scalar=existing)])
    if operation == "allocation":
        result = request_allocation(session, actor_user_id=actor, idempotency_key="stable-key",
                                    command=command, policy=Policy())
    else:
        result = record_return(session, actor_user_id=actor, idempotency_key="stable-key",
                               command=command, policy=Policy())
    assert result.id == resource_id
    assert result.replayed is True
    assert session.flushes == 0


def test_allocation_approval_denial_is_fail_closed_before_database_access():
    actor = uuid4()
    session = Session([])
    with pytest.raises(AppError) as error:
        decide_allocation(session, allocation_id=uuid4(), actor_user_id=actor,
                          decision="approved", policy=Policy(False))
    assert error.value.status_code == 403
    assert session.flushes == 0


def test_allocation_cannot_be_approved_by_requester():
    actor = uuid4()
    allocation = SimpleNamespace(id=uuid4(), status="pending")
    approval = SimpleNamespace(requested_by_id=actor, status="pending", decided_by_id=None,
                               decided_at=None, decision_reason_code=None)
    session = Session([Result(scalar=allocation), Result(scalar=approval)])
    with pytest.raises(AppError) as error:
        decide_allocation(session, allocation_id=allocation.id, actor_user_id=actor,
                          decision="approved", policy=Policy())
    assert error.value.code == "SELF_APPROVAL_DENIED"
    assert session.flushes == 0


def test_allocation_decision_rejects_unstructured_reason_codes():
    session = Session([])
    with pytest.raises(AppError) as error:
        decide_allocation(session, allocation_id=uuid4(), actor_user_id=uuid4(),
                          decision="approved", reason_code="Private employee details", policy=Policy())
    assert error.value.code == "INVALID_DECISION"
    assert session.flushes == 0


def test_damaged_quantity_return_is_recorded_for_quarantine_after_verification():
    actor = uuid4()
    line = SimpleNamespace(id=uuid4(), allocation_id=uuid4(), status="active", tracked_asset_id=None,
                           product_id=uuid4(), location_id=uuid4(), returned_quantity=0, quantity=2,
                           unit="each")
    allocation = SimpleNamespace(employee_id=uuid4())
    session = Session([Result(scalar=None), Result(scalar=line), Result(scalar=allocation)])
    command = ReturnCreate(allocation_line_id=line.id, quantity="1", condition="damaged")
    result = record_return(session, actor_user_id=actor, idempotency_key="fictional-return",
                           command=command, policy=Policy(), audit_writer=lambda *_: None)
    assert result.status == "pending_verification"
    returned = next(row for row in session.added if row.__class__.__name__ == "InventoryReturn")
    approval = next(row for row in session.added if row.__class__.__name__ == "WorkflowApproval")
    assert returned.condition == "damaged"
    assert returned.status == "pending"
    assert approval.entity_type == "return"


def test_verified_damaged_quantity_return_moves_reserved_stock_to_quarantine():
    actor, requester = uuid4(), uuid4()
    returned = SimpleNamespace(id=uuid4(), status="pending", recorded_by_id=requester,
        allocation_line_id=uuid4(), quantity=Decimal("1.250"), condition="damaged",
        idempotency_request_id=uuid4())
    approval = SimpleNamespace(status="pending", decided_by_id=None, decided_at=None,
        decision_reason_code=None, requested_by_id=requester)
    line = SimpleNamespace(id=returned.allocation_line_id, allocation_id=uuid4(), status="active",
        quantity=Decimal("2.000"), returned_quantity=Decimal("0"), tracked_asset_id=None,
        product_id=uuid4(), location_id=uuid4(), unit="box")
    allocation = SimpleNamespace(status="issued", employee_id=uuid4())
    balance = SimpleNamespace(on_hand=Decimal("2.000"), reserved=Decimal("1.250"),
        quarantined=Decimal("0"))
    session = Session([Result(scalar=returned), Result(scalar=approval), Result(scalar=line),
        Result(scalar=allocation), Result(scalar=balance), Result(first=None)])
    decide_return(session, return_id=returned.id, actor_user_id=actor,
        decision="approved", policy=Policy(), audit_writer=lambda *_: None)
    movement = next(row for row in session.added if row.__class__.__name__ == "InventoryMovement")
    assert returned.status == "verified"
    assert balance.on_hand == Decimal("2.000")
    assert balance.reserved == Decimal("0")
    assert balance.quarantined == Decimal("1.250")
    assert movement.movement_type == "quarantine"
    assert movement.reserved_delta == Decimal("-1.250")
    assert movement.quarantined_delta == Decimal("1.250")


def test_approved_individual_allocation_issues_after_current_stock_and_employee_checks():
    actor, requester, employee_id, asset_id = uuid4(), uuid4(), uuid4(), uuid4()
    allocation = SimpleNamespace(id=uuid4(), status="approved", requested_by_id=requester,
                                  employee_id=employee_id, idempotency_request_id=uuid4())
    approval = SimpleNamespace(decided_by_id=actor)
    line = SimpleNamespace(allocation_id=allocation.id, status="pending", tracked_asset_id=asset_id,
                           product_id=None, location_id=None, unit=None, quantity=1,
                           returned_quantity=0)
    employee = SimpleNamespace(status="active")
    asset = SimpleNamespace(lifecycle_status="available")
    session = Session([Result(scalar=allocation), Result(scalar=approval), Result(scalar=line),
                       Result(scalar=employee), Result(scalar=asset), Result(first=None)])
    audits = []
    issue_allocation(session, allocation_id=allocation.id, actor_user_id=actor,
                     policy=Policy(), audit_writer=lambda _session, event: audits.append(event))
    assert allocation.status == "issued"
    assert line.status == "active"
    assert asset.lifecycle_status == "allocated"
    assert audits[0].updated_values["allocation_status"] == "issued"


def test_individual_return_verification_closes_custody_with_audit():
    actor, requester, asset_id = uuid4(), uuid4(), uuid4()
    returned = SimpleNamespace(id=uuid4(), status="pending", recorded_by_id=requester,
                               allocation_line_id=uuid4(), quantity=1, condition="good",
                               idempotency_request_id=uuid4())
    approval = SimpleNamespace(status="pending", decided_by_id=None, decided_at=None)
    line = SimpleNamespace(id=returned.allocation_line_id, allocation_id=uuid4(), status="active",
                           quantity=1, returned_quantity=0, tracked_asset_id=asset_id,
                           product_id=None, location_id=None, unit=None)
    asset = SimpleNamespace(lifecycle_status="allocated")
    allocation = SimpleNamespace(status="issued", employee_id=uuid4())
    session = Session([Result(scalar=returned), Result(scalar=approval), Result(scalar=line),
                       Result(scalar=allocation), Result(scalar=asset), Result(first=None)])
    audits = []
    decide_return(session, return_id=returned.id, actor_user_id=actor, decision="approved",
                  policy=Policy(), audit_writer=lambda _session, event: audits.append(event))
    assert returned.status == "verified"
    assert approval.status == "approved"
    assert line.returned_quantity == 1
    assert line.status == "returned"
    assert allocation.status == "returned"
    assert asset.lifecycle_status == "available"
    assert audits[0].previous_values == {
        "approval_status": "pending", "allocation_status": "issued", "returned_quantity": 0,
    }
    assert audits[0].updated_values == {
        "approval_status": "approved", "allocation_status": "returned", "returned_quantity": 1,
    }


def test_inventory_write_router_exposes_transaction_contract_but_stays_isolated():
    from app.api.v1.router import api_router
    from app.api.v1.routes.inventory_writes import build_inventory_write_router

    candidate = build_inventory_write_router(
        principal_dependency=lambda: None, session_dependency=lambda: None,
        write_policy_dependency=lambda: None, csrf_dependency=lambda: None,
    )
    paths = {route.path for route in candidate.routes}
    assert "/inventory/allocations" in paths
    assert "/inventory/returns" in paths
    operational_paths = {route.path for included in api_router.routes
                          for route in included.original_router.routes}
    assert "/inventory/allocations" not in operational_paths
    assert "/inventory/returns" not in operational_paths
