"""Rollback-isolated PostgreSQL registration/allocation/return workflow check."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_integration_test_settings
from app.core.errors import AppError
from app.core.integration_test_config import require_owner_test_url
from app.models import (
    AllocationLine,
    AssetCategory,
    Department,
    Designation,
    Employee,
    InventoryBalance,
    InventoryReturn,
    Location,
    ReceiptLine,
    Team,
    TrackedAsset,
    User,
    WorkflowApproval,
)
from app.schemas.inventory import ProductCreate, ReceiptCreate, ReceiptLineCreate
from app.schemas.transactions import AllocationCreate, ReturnCreate
from app.services.audit import write_audit_event
from app.services.inventory_transactions import (
    decide_allocation,
    decide_return,
    issue_allocation,
    record_return,
    request_allocation,
)
from app.services.inventory_writes import (
    create_product,
    create_receipt,
    decide_registration_approval,
    finalize_asset_registration,
    finalize_quantity_registration,
    submit_asset_registration,
    submit_quantity_registration,
)
from app.services.quantity_disposition import (
    decide_quantity_disposition,
    finalize_quantity_disposition,
    request_quantity_disposition,
)
from app.services.workflow_operations import (
    complete_repair,
    decide_disposal,
    decide_exit_clearance,
    decide_repair,
    finalize_disposal,
    open_exit_clearance,
    request_disposal,
    request_repair,
)
from app.services.workflows import complete_exit_clearance

pytestmark = pytest.mark.integration


class FictionalPolicy:
    def authorize(self, *, actor_user_id, capability, entity_type, entity_id=None):
        return True

    def requires_approval(self, *, action):
        # Receiving/product policy is a fictional rehearsal setting only.
        return action == "allocation_issue"

    def approval_satisfied(self, *, action, entity_id, actor_user_id):
        return True

    def allows_disposal_reason(self, reason_code):
        return reason_code == "obsolete"


@pytest.fixture
def workflow_session():
    settings = get_integration_test_settings()
    engine = create_engine(require_owner_test_url(settings.owner_database_url),
                           pool_pre_ping=True, hide_parameters=True)
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
        identity = connection.execute(text(
            "SELECT current_database(), session_user, current_user, inet_server_port(), "
            "(SELECT version_num FROM public.alembic_version)"
        )).one()
        assert identity == (
            "inventory_aios_restore_check", "inventory_aios_migrator", "inventory_aios_owner",
            5432, "d2a8f4c1b790",
        )
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
        engine.dispose()


def test_registration_approval_asset_and_quantity_allocation_return(workflow_session: Session) -> None:
    suffix = uuid4().hex
    actor = User(username=f"TEST_ACTOR_{suffix}", email=f"actor-{suffix}@example.invalid",
                 display_name="TEST Actor", status="active")
    reviewer = User(username=f"TEST_REVIEWER_{suffix}", email=f"reviewer-{suffix}@example.invalid",
                    display_name="TEST Reviewer", status="active")
    department = Department(code=f"TEST-{suffix}", name="TEST department")
    individual_category = AssetCategory(code=f"TEST-I-{suffix}", name="TEST individual",
                                        tracking_mode="individual")
    quantity_category = AssetCategory(code=f"TEST-Q-{suffix}", name="TEST quantity",
                                      tracking_mode="quantity")
    location = Location(code=f"TEST-{suffix}", name="TEST location", active=True)
    workflow_session.add_all((actor, reviewer, department, individual_category, quantity_category, location))
    workflow_session.flush()
    team = Team(department_id=department.id, code=f"TEST-{suffix}", name="TEST team")
    designation = Designation(code=f"TEST-{suffix}", name="TEST designation")
    workflow_session.add_all((team, designation))
    workflow_session.flush()
    employee = Employee(employee_number=f"TEST-{suffix}", first_name="Fictional", last_name="Employee",
                        department_id=department.id, team_id=team.id, designation_id=designation.id,
                        status="active")
    workflow_session.add(employee)
    workflow_session.flush()
    workflow_session.commit()

    policy = FictionalPolicy()
    individual_product = create_product(
        workflow_session, actor_user_id=actor.id, idempotency_key=f"product-i-{suffix}",
        command=ProductCreate(category_id=individual_category.id, name="TEST laptop"),
        policy=policy, audit_writer=write_audit_event,
    )
    quantity_product = create_product(
        workflow_session, actor_user_id=actor.id, idempotency_key=f"product-q-{suffix}",
        command=ProductCreate(category_id=quantity_category.id, name="TEST cable"),
        policy=policy, audit_writer=write_audit_event,
    )
    receipt = create_receipt(
        workflow_session, actor_user_id=actor.id, idempotency_key=f"receipt-{suffix}",
        command=ReceiptCreate(
            received_at=datetime.now(UTC), location_id=location.id,
            lines=[
                ReceiptLineCreate(product_id=individual_product.id, quantity=Decimal("1"),
                                  unit="asset", tracking_mode="individual"),
                ReceiptLineCreate(product_id=quantity_product.id, quantity=Decimal("10"),
                                  unit="each", tracking_mode="quantity"),
            ],
        ),
        policy=policy, audit_writer=write_audit_event,
    )
    lines = workflow_session.scalars(select(ReceiptLine).where(
        ReceiptLine.receipt_id == receipt.id).order_by(ReceiptLine.tracking_mode)).all()
    individual_line = next(line for line in lines if line.tracking_mode == "individual")
    quantity_line = next(line for line in lines if line.tracking_mode == "quantity")

    asset_request = submit_asset_registration(
        workflow_session, actor_user_id=actor.id, idempotency_key=f"asset-reg-{suffix}",
        receipt_line_id=individual_line.id, asset_number=None, serial_number=None, condition="good",
        policy=policy, audit_writer=write_audit_event,
    )
    quantity_request = submit_quantity_registration(
        workflow_session, actor_user_id=actor.id, idempotency_key=f"qty-reg-{suffix}",
        receipt_line_id=quantity_line.id, quantity=Decimal("10"), unit="each",
        policy=policy, audit_writer=write_audit_event,
    )
    for entity_type, entity_id in (("asset_registration", asset_request.id),
                                   ("quantity_registration", quantity_request.id)):
        approval = workflow_session.scalar(select(WorkflowApproval).where(
            WorkflowApproval.entity_type == entity_type,
            WorkflowApproval.entity_id == entity_id,
            WorkflowApproval.status == "pending",
        ))
        assert approval is not None and approval.requested_by_id == actor.id
        decide_registration_approval(
            workflow_session, approval_id=approval.id, actor_user_id=reviewer.id,
            decision="approved", reason_code="checked", policy=policy, audit_writer=write_audit_event,
        )

    asset_result = finalize_asset_registration(
        workflow_session, request_id=asset_request.id, actor_user_id=actor.id,
        policy=policy, audit_writer=write_audit_event,
    )
    quantity_result = finalize_quantity_registration(
        workflow_session, request_id=quantity_request.id, actor_user_id=actor.id,
        policy=policy, audit_writer=write_audit_event,
    )
    asset = workflow_session.get(TrackedAsset, asset_result.id)
    balance = workflow_session.scalar(select(InventoryBalance).where(
        InventoryBalance.product_id == quantity_product.id,
        InventoryBalance.location_id == location.id,
        InventoryBalance.unit == "each",
    ))
    assert asset is not None and asset.lifecycle_status == "available"
    assert balance is not None and Decimal(balance.on_hand) == Decimal("10")
    assert quantity_result.status == "registered"

    asset_allocation = request_allocation(
        workflow_session, actor_user_id=actor.id, idempotency_key=f"alloc-asset-{suffix}",
        command=AllocationCreate(employee_id=employee.id, tracked_asset_id=asset.id),
        policy=policy, audit_writer=write_audit_event,
    )
    decide_allocation(workflow_session, allocation_id=asset_allocation.id, actor_user_id=reviewer.id,
                      decision="approved", policy=policy, audit_writer=write_audit_event)
    issue_allocation(workflow_session, allocation_id=asset_allocation.id, actor_user_id=actor.id,
                     policy=policy, audit_writer=write_audit_event)
    asset_line = workflow_session.scalar(select(AllocationLine).where(
        AllocationLine.allocation_id == asset_allocation.id))
    assert asset_line is not None and asset_line.status == "active"
    with pytest.raises(AppError):
        request_allocation(
            workflow_session, actor_user_id=actor.id, idempotency_key=f"alloc-duplicate-{suffix}",
            command=AllocationCreate(employee_id=employee.id, tracked_asset_id=asset.id),
            policy=policy, audit_writer=write_audit_event,
        )
    asset_return = record_return(
        workflow_session, actor_user_id=actor.id, idempotency_key=f"return-asset-{suffix}",
        command=ReturnCreate(allocation_line_id=asset_line.id, quantity=Decimal("1"), condition="good"),
        policy=policy, audit_writer=write_audit_event,
    )
    decide_return(workflow_session, return_id=asset_return.id, actor_user_id=reviewer.id,
                  decision="approved", policy=policy, audit_writer=write_audit_event)
    workflow_session.refresh(asset)
    assert asset.lifecycle_status == "available"
    assert workflow_session.get(InventoryReturn, asset_return.id).status == "verified"

    quantity_allocation = request_allocation(
        workflow_session, actor_user_id=actor.id, idempotency_key=f"alloc-qty-{suffix}",
        command=AllocationCreate(employee_id=employee.id, product_id=quantity_product.id,
                                 location_id=location.id, unit="each", quantity=Decimal("4")),
        policy=policy, audit_writer=write_audit_event,
    )
    decide_allocation(workflow_session, allocation_id=quantity_allocation.id, actor_user_id=reviewer.id,
                      decision="approved", policy=policy, audit_writer=write_audit_event)
    issue_allocation(workflow_session, allocation_id=quantity_allocation.id, actor_user_id=actor.id,
                     policy=policy, audit_writer=write_audit_event)
    quantity_line_row = workflow_session.scalar(select(AllocationLine).where(
        AllocationLine.allocation_id == quantity_allocation.id))
    assert quantity_line_row is not None
    quantity_return = record_return(
        workflow_session, actor_user_id=actor.id, idempotency_key=f"return-qty-{suffix}",
        command=ReturnCreate(allocation_line_id=quantity_line_row.id,
                             quantity=Decimal("2"), condition="good"),
        policy=policy, audit_writer=write_audit_event,
    )
    decide_return(workflow_session, return_id=quantity_return.id, actor_user_id=reviewer.id,
                  decision="approved", policy=policy, audit_writer=write_audit_event)
    workflow_session.refresh(balance)
    assert Decimal(balance.on_hand) == Decimal("10")
    assert Decimal(balance.reserved) == Decimal("2")
    assert workflow_session.get(InventoryReturn, quantity_return.id).status == "verified"

    damaged_return = record_return(
        workflow_session, actor_user_id=actor.id, idempotency_key=f"return-damaged-{suffix}",
        command=ReturnCreate(allocation_line_id=quantity_line_row.id,
                             quantity=Decimal("1"), condition="damaged"),
        policy=policy, audit_writer=write_audit_event,
    )
    decide_return(workflow_session, return_id=damaged_return.id, actor_user_id=reviewer.id,
                  decision="approved", policy=policy, audit_writer=write_audit_event)
    workflow_session.refresh(balance)
    assert Decimal(balance.quarantined) == Decimal("1")
    assert Decimal(balance.reserved) == Decimal("1")
    disposition_id = request_quantity_disposition(
        workflow_session, return_id=damaged_return.id, actor_user_id=actor.id,
        quantity=Decimal("1"), disposition="release", idempotency_key=f"release-{suffix}",
        policy=policy,
    )
    decide_quantity_disposition(workflow_session, request_id=disposition_id,
        actor_user_id=reviewer.id, decision="approved", reason_code="checked", policy=policy)
    finalize_quantity_disposition(workflow_session, request_id=disposition_id,
        actor_user_id=actor.id, policy=policy)
    workflow_session.refresh(balance)
    assert Decimal(balance.quarantined) == Decimal("0")
    assert Decimal(balance.on_hand) == Decimal("10")

    final_return = record_return(
        workflow_session, actor_user_id=actor.id, idempotency_key=f"return-final-{suffix}",
        command=ReturnCreate(allocation_line_id=quantity_line_row.id,
                             quantity=Decimal("1"), condition="good"),
        policy=policy, audit_writer=write_audit_event,
    )
    decide_return(workflow_session, return_id=final_return.id, actor_user_id=reviewer.id,
                  decision="approved", policy=policy, audit_writer=write_audit_event)

    repair_id = request_repair(workflow_session, asset_id=asset.id, actor_user_id=actor.id,
        issue_details="TEST damaged component", provider="TEST provider",
        idempotency_key=f"repair-{suffix}", policy=policy)
    decide_repair(workflow_session, repair_id=repair_id, actor_user_id=reviewer.id,
        decision="approved", reason_code="checked", policy=policy)
    complete_repair(workflow_session, repair_id=repair_id, actor_user_id=actor.id,
        condition="good", notes="TEST repaired", cost_amount=None, cost_currency=None, policy=policy)
    workflow_session.refresh(asset)
    assert asset.lifecycle_status == "available"

    disposal_id = request_disposal(workflow_session, asset_id=asset.id, actor_user_id=actor.id,
        reason_code="obsolete", condition="good", idempotency_key=f"dispose-{suffix}", policy=policy)
    decide_disposal(workflow_session, request_id=disposal_id, actor_user_id=reviewer.id,
        decision="approved", reason_code="checked", policy=policy)
    finalize_disposal(workflow_session, request_id=disposal_id, actor_user_id=actor.id, policy=policy)
    workflow_session.refresh(asset)
    assert asset.lifecycle_status == "disposed"

    clearance_id = open_exit_clearance(workflow_session, employee_id=employee.id,
        actor_user_id=actor.id, policy=policy)
    decide_exit_clearance(workflow_session, clearance_id=clearance_id,
        actor_user_id=reviewer.id, decision="approved", policy=policy)
    complete_exit_clearance(workflow_session, clearance_id=clearance_id,
        actor_user_id=actor.id, policy=policy)
