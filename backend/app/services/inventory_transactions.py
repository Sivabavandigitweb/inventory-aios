"""Policy-gated allocation and return transactions.

Every allocation/return is a single-line transaction. Multi-item requests are
represented as separate independently approved transactions. The caller owns
the outer transaction and must commit before returning success.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    Allocation,
    AllocationLine,
    DisposalRequest,
    Employee,
    InventoryBalance,
    InventoryMovement,
    InventoryProduct,
    InventoryReturn,
    TrackedAsset,
    WorkflowApproval,
)
from app.schemas.inventory import WriteResult
from app.schemas.transactions import AllocationCreate, AllocationRead, ReturnCreate, ReturnRead
from app.services.audit import AuditEventInput, write_audit_event
from app.services.inventory_writes import (
    InventoryWritePolicy,
    _authorize,
    _idempotent,
    _self_approval_allowed,
)

AuditWriter = Callable[[Session, AuditEventInput], object]


def request_allocation(
    session: Session, *, actor_user_id: UUID, idempotency_key: str,
    command: AllocationCreate, policy: InventoryWritePolicy | None,
    audit_writer: AuditWriter = write_audit_event,
) -> WriteResult:
    _authorize(policy, actor=actor_user_id, capability="allocations:create",
               entity_type="employee", entity_id=command.employee_id)
    payload = command.model_dump(mode="json")

    def create(request_id: UUID) -> tuple[UUID, str]:
        employee = session.execute(select(Employee).where(Employee.id == command.employee_id)
                                   .with_for_update()).scalar_one_or_none()
        if employee is None or employee.status != "active":
            raise AppError("EMPLOYEE_INELIGIBLE", "An active employee is required.", 409)
        if command.tracked_asset_id:
            _authorize(policy, actor=actor_user_id, capability="assets:read",
                       entity_type="tracked_asset", entity_id=command.tracked_asset_id)
            asset = session.execute(select(TrackedAsset).where(
                TrackedAsset.id == command.tracked_asset_id).with_for_update()).scalar_one_or_none()
            if asset is None or asset.lifecycle_status != "available":
                raise AppError("ASSET_UNAVAILABLE", "The selected asset is not available.", 409)
            pending_disposal = session.execute(select(DisposalRequest.id).where(
                DisposalRequest.tracked_asset_id == command.tracked_asset_id,
                DisposalRequest.status.in_(("pending", "approved")))).first()
            if pending_disposal:
                raise AppError("ASSET_UNAVAILABLE", "The selected asset is under disposal review.", 409)
            existing = session.execute(select(AllocationLine.id).where(
                AllocationLine.tracked_asset_id == command.tracked_asset_id,
                AllocationLine.status.in_(("pending", "active", "partially_returned")),
            ).with_for_update()).first()
            if existing:
                raise AppError("ASSET_ALREADY_ASSIGNED", "The selected asset already has an active allocation.", 409)
        else:
            _authorize(policy, actor=actor_user_id, capability="inventory:quantity:read",
                       entity_type="inventory_balance", entity_id=command.product_id)
            _authorize(policy, actor=actor_user_id, capability="inventory:quantity:read",
                       entity_type="location", entity_id=command.location_id)
            product = session.execute(select(InventoryProduct).where(
                InventoryProduct.id == command.product_id, InventoryProduct.active.is_(True)
            ).with_for_update()).scalar_one_or_none()
            if product is None:
                raise AppError("INVENTORY_UNAVAILABLE", "The selected quantity inventory is unavailable.", 409)
            balance = session.execute(select(InventoryBalance).where(
                InventoryBalance.product_id == command.product_id,
                InventoryBalance.location_id == command.location_id,
                InventoryBalance.unit == command.unit,
            ).with_for_update()).scalar_one_or_none()
            if balance is None or Decimal(balance.on_hand) - Decimal(balance.reserved) - Decimal(balance.quarantined) < command.quantity:
                raise AppError("INSUFFICIENT_STOCK", "Available quantity is insufficient.", 409)
        allocation = Allocation(employee_id=command.employee_id, requested_by_id=actor_user_id,
                                status="pending", idempotency_request_id=request_id)
        session.add(allocation)
        session.flush()
        line = AllocationLine(
            allocation_id=allocation.id, tracked_asset_id=command.tracked_asset_id,
            product_id=command.product_id, location_id=command.location_id,
            unit=command.unit, quantity=command.quantity, returned_quantity=Decimal("0"),
            status="pending",
        )
        session.add(line)
        session.flush()
        session.add(WorkflowApproval(
            entity_type="allocation", entity_id=allocation.id,
            required_capability="approvals:decide:allocation", status="pending",
            requested_by_id=actor_user_id,
        ))
        audit_writer(session, AuditEventInput(
            actor_user_id=actor_user_id, action="inventory.allocation_requested",
            entity_type="allocation", entity_id=allocation.id,
            metadata={"changed_fields": ["allocation_status", "quantity"]},
            updated_values={"allocation_status": "pending", "quantity": command.quantity},
        ))
        return allocation.id, "pending_approval"

    return _idempotent(session, actor=actor_user_id, scope="inventory.allocation.request",
                       key=idempotency_key, payload=payload, create=create)


def decide_allocation(
    session: Session, *, allocation_id: UUID, actor_user_id: UUID, decision: str,
    reason_code: str | None = None,
    policy: InventoryWritePolicy | None, audit_writer: AuditWriter = write_audit_event,
) -> None:
    if decision not in {"approved", "rejected"}:
        raise AppError("INVALID_DECISION", "The approval decision is invalid.", 422)
    if reason_code is not None and (not 1 <= len(reason_code) <= 40
                                    or not reason_code[0].islower()
                                    or any(not (char.islower() or char.isdigit() or char in "_.-")
                                           for char in reason_code)):
        raise AppError("INVALID_DECISION", "The approval reason code is invalid.", 422)
    _authorize(policy, actor=actor_user_id, capability="approvals:decide:allocation",
               entity_type="allocation", entity_id=allocation_id)
    try:
        with session.begin_nested():
            allocation = session.execute(select(Allocation).where(
                Allocation.id == allocation_id).with_for_update()).scalar_one_or_none()
            approval = session.execute(select(WorkflowApproval).where(
                WorkflowApproval.entity_type == "allocation",
                WorkflowApproval.entity_id == allocation_id,
                WorkflowApproval.status == "pending",
            ).with_for_update()).scalar_one_or_none()
            if allocation is None or approval is None or allocation.status != "pending":
                raise AppError("APPROVAL_UNAVAILABLE", "A pending allocation approval was not found.", 409)
            if approval.requested_by_id == actor_user_id and not _self_approval_allowed(policy, "allocation"):
                raise AppError("SELF_APPROVAL_DENIED", "The requester cannot approve their own allocation.", 403)
            approval.status = decision
            approval.decided_by_id = actor_user_id
            approval.decided_at = datetime.now(timezone.utc)
            approval.decision_reason_code = reason_code
            allocation.status = decision
            lines = session.execute(select(AllocationLine).where(
                AllocationLine.allocation_id == allocation_id).with_for_update()).scalars().all()
            for line in lines:
                line.status = "pending" if decision == "approved" else "cancelled"
            audit_writer(session, AuditEventInput(
                actor_user_id=actor_user_id, action="inventory.allocation_decided",
                entity_type="allocation", entity_id=allocation_id,
                metadata={"changed_fields": ["allocation_status", "approval_status"]},
                previous_values={"allocation_status": "pending", "approval_status": "pending"},
                updated_values={"allocation_status": decision, "approval_status": decision},
            ))
            session.flush()
    except AppError:
        raise
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The allocation decision could not be recorded.", 503) from None


def issue_allocation(
    session: Session, *, allocation_id: UUID, actor_user_id: UUID,
    policy: InventoryWritePolicy | None, audit_writer: AuditWriter = write_audit_event,
) -> None:
    _authorize(policy, actor=actor_user_id, capability="allocations:update",
               entity_type="allocation", entity_id=allocation_id)
    if policy is None:
        raise AppError("WORKFLOW_UNAVAILABLE", "Allocation policy is unavailable.", 503)
    try:
        if policy.requires_approval(action="allocation_issue") is not True:
            raise AppError("WORKFLOW_UNAVAILABLE", "Independent allocation approval is required.", 503)
    except AppError:
        raise
    except Exception:
        raise AppError("WORKFLOW_UNAVAILABLE", "Allocation policy is unavailable.", 503) from None
    try:
        with session.begin_nested():
            allocation = session.execute(select(Allocation).where(
                Allocation.id == allocation_id).with_for_update()).scalar_one_or_none()
            approval = session.execute(select(WorkflowApproval).where(
                WorkflowApproval.entity_type == "allocation", WorkflowApproval.entity_id == allocation_id,
                WorkflowApproval.status == "approved",
            ).with_for_update()).scalar_one_or_none()
            if allocation is None or allocation.status != "approved" or approval is None:
                raise AppError("APPROVAL_REQUIRED", "An independent allocation approval is required.", 403)
            if approval.decided_by_id == allocation.requested_by_id and not _self_approval_allowed(policy, "allocation"):
                raise AppError("SELF_APPROVAL_DENIED", "The requester cannot approve their own allocation.", 403)
            if policy.approval_satisfied(action="allocation_issue", entity_id=allocation_id,
                                         actor_user_id=actor_user_id) is not True:
                raise AppError("APPROVAL_REQUIRED", "Current allocation approval is unavailable.", 403)
            line = session.execute(select(AllocationLine).where(
                AllocationLine.allocation_id == allocation_id).with_for_update()).scalar_one_or_none()
            employee = session.execute(select(Employee).where(
                Employee.id == allocation.employee_id).with_for_update()).scalar_one_or_none()
            if line is None or line.status != "pending" or employee is None or employee.status != "active":
                raise AppError("ALLOCATION_INELIGIBLE", "The allocation is no longer eligible.", 409)
            _authorize(policy, actor=actor_user_id, capability="allocations:update",
                       entity_type="employee", entity_id=allocation.employee_id)
            before: str | Decimal
            after: str | Decimal
            if line.tracked_asset_id:
                _authorize(policy, actor=actor_user_id, capability="assets:update",
                           entity_type="tracked_asset", entity_id=line.tracked_asset_id)
                asset = session.execute(select(TrackedAsset).where(
                    TrackedAsset.id == line.tracked_asset_id).with_for_update()).scalar_one_or_none()
                if asset is None or asset.lifecycle_status != "available":
                    raise AppError("ASSET_UNAVAILABLE", "The asset is no longer available.", 409)
                pending_disposal = session.execute(select(DisposalRequest.id).where(
                    DisposalRequest.tracked_asset_id == line.tracked_asset_id,
                    DisposalRequest.status.in_(("pending", "approved")))).first()
                if pending_disposal:
                    raise AppError("ASSET_UNAVAILABLE", "The asset is under disposal review.", 409)
                before = asset.lifecycle_status
                asset.lifecycle_status = "allocated"
                after = asset.lifecycle_status
                resource_field = "lifecycle_status"
                resource_changed_fields = ["lifecycle_status"]
            else:
                _authorize(policy, actor=actor_user_id, capability="inventory:quantity:adjust",
                           entity_type="location", entity_id=line.location_id)
                balance = session.execute(select(InventoryBalance).where(
                    InventoryBalance.product_id == line.product_id,
                    InventoryBalance.location_id == line.location_id,
                    InventoryBalance.unit == line.unit,
                ).with_for_update()).scalar_one_or_none()
                if balance is None or Decimal(balance.on_hand) - Decimal(balance.reserved) - Decimal(balance.quarantined) < Decimal(line.quantity):
                    raise AppError("INSUFFICIENT_STOCK", "Available quantity is insufficient.", 409)
                before = Decimal(balance.reserved)
                balance.reserved = Decimal(balance.reserved) + Decimal(line.quantity)
                after = Decimal(balance.reserved)
                resource_field = "reserved"
                resource_changed_fields = ["reserved"]
                session.add(InventoryMovement(
                    product_id=line.product_id, location_id=line.location_id, unit=line.unit,
                    quantity_delta=-Decimal(line.quantity), reserved_delta=Decimal(line.quantity), movement_type="allocation",
                    actor_user_id=actor_user_id, idempotency_request_id=allocation.idempotency_request_id,
                    reference_type="allocation", reference_id=allocation.id,
                ))
            line.status = "active"
            allocation.status = "issued"
            audit_writer(session, AuditEventInput(
                actor_user_id=actor_user_id, action="inventory.allocation_issued",
                entity_type="allocation", entity_id=allocation_id,
                metadata={"changed_fields": ["allocation_status", *resource_changed_fields]},
                previous_values={"allocation_status": "approved", resource_field: before},
                updated_values={"allocation_status": "issued", resource_field: after},
            ))
            session.flush()
    except AppError:
        raise
    except IntegrityError:
        raise AppError("INVENTORY_CONFLICT", "The allocation conflicts with current inventory.", 409) from None
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The allocation could not be issued.", 503) from None
    except Exception:
        raise AppError("WORKFLOW_UNAVAILABLE", "Allocation approval is unavailable.", 503) from None


def record_return(
    session: Session, *, actor_user_id: UUID, idempotency_key: str,
    command: ReturnCreate, policy: InventoryWritePolicy | None,
    audit_writer: AuditWriter = write_audit_event,
) -> WriteResult:
    _authorize(policy, actor=actor_user_id, capability="returns:record",
               entity_type="allocation_line", entity_id=command.allocation_line_id)
    payload = command.model_dump(mode="json")

    def create(request_id: UUID) -> tuple[UUID, str]:
        line = session.execute(select(AllocationLine).where(
            AllocationLine.id == command.allocation_line_id).with_for_update()).scalar_one_or_none()
        if line is None or line.status not in {"active", "partially_returned"}:
            raise AppError("ALLOCATION_NOT_ACTIVE", "The allocation is not available for return.", 409)
        allocation = session.execute(select(Allocation).where(
            Allocation.id == line.allocation_id).with_for_update()).scalar_one_or_none()
        if allocation is None:
            raise AppError("WORKFLOW_INCONSISTENT", "The allocation is unavailable.", 409)
        _authorize(policy, actor=actor_user_id, capability="returns:record",
                   entity_type="employee", entity_id=allocation.employee_id)
        if line.tracked_asset_id is not None:
            _authorize(policy, actor=actor_user_id, capability="assets:read",
                       entity_type="tracked_asset", entity_id=line.tracked_asset_id)
        else:
            _authorize(policy, actor=actor_user_id, capability="inventory:quantity:read",
                       entity_type="inventory_balance", entity_id=line.product_id)
            _authorize(policy, actor=actor_user_id, capability="inventory:quantity:read",
                       entity_type="location", entity_id=line.location_id)
        if line.tracked_asset_id is not None and command.quantity != Decimal("1"):
            raise AppError("INVALID_RETURN_QUANTITY", "An individual asset return has quantity one.", 422)
        if line.tracked_asset_id is None and command.condition not in {"good", "damaged"}:
            raise AppError("RETURN_CONDITION_UNSUPPORTED", "Quantity returns must be recorded as good or damaged.", 422)
        pending = session.scalar(select(func.coalesce(func.sum(InventoryReturn.quantity), 0)).where(
            InventoryReturn.allocation_line_id == line.id, InventoryReturn.status == "pending")) or Decimal("0")
        if Decimal(line.returned_quantity) + Decimal(pending) + command.quantity > Decimal(line.quantity):
            raise AppError("RETURN_EXCEEDS_ALLOCATION", "The return exceeds the outstanding allocation.", 409)
        returned = InventoryReturn(
            allocation_line_id=line.id, quantity=command.quantity, condition=command.condition,
            status="pending", recorded_by_id=actor_user_id, idempotency_request_id=request_id,
        )
        session.add(returned)
        session.flush()
        session.add(WorkflowApproval(
            entity_type="return", entity_id=returned.id,
            required_capability="approvals:decide:return", status="pending",
            requested_by_id=actor_user_id,
        ))
        audit_writer(session, AuditEventInput(
            actor_user_id=actor_user_id, action="inventory.return_recorded",
            entity_type="inventory_return", entity_id=returned.id,
            metadata={"changed_fields": ["approval_status", "quantity", "condition"]},
            updated_values={"approval_status": "pending", "quantity": command.quantity,
                            "condition": command.condition},
        ))
        return returned.id, "pending_verification"

    try:
        return _idempotent(session, actor=actor_user_id, scope="inventory.return.record",
                           key=idempotency_key, payload=payload, create=create)
    except AppError:
        raise
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The return could not be recorded.", 503) from None


def decide_return(
    session: Session, *, return_id: UUID, actor_user_id: UUID, decision: str,
    reason_code: str | None = None,
    policy: InventoryWritePolicy | None, audit_writer: AuditWriter = write_audit_event,
) -> None:
    if decision not in {"approved", "rejected"}:
        raise AppError("INVALID_DECISION", "The return decision is invalid.", 422)
    if reason_code is not None and (not 1 <= len(reason_code) <= 40
                                    or not reason_code[0].islower()
                                    or any(not (char.islower() or char.isdigit() or char in "_.-")
                                           for char in reason_code)):
        raise AppError("INVALID_DECISION", "The approval reason code is invalid.", 422)
    _authorize(policy, actor=actor_user_id, capability="returns:verify",
               entity_type="inventory_return", entity_id=return_id)
    _authorize(policy, actor=actor_user_id, capability="approvals:decide:return",
               entity_type="inventory_return", entity_id=return_id)
    try:
        with session.begin_nested():
            returned = session.execute(select(InventoryReturn).where(
                InventoryReturn.id == return_id).with_for_update()).scalar_one_or_none()
            approval = session.execute(select(WorkflowApproval).where(
                WorkflowApproval.entity_type == "return", WorkflowApproval.entity_id == return_id,
                WorkflowApproval.status == "pending",
            ).with_for_update()).scalar_one_or_none()
            if returned is None or approval is None or returned.status != "pending":
                raise AppError("RETURN_UNAVAILABLE", "A pending return was not found.", 409)
            if returned.recorded_by_id == actor_user_id and not _self_approval_allowed(policy, "return"):
                raise AppError("SELF_APPROVAL_DENIED", "The return recorder cannot verify their own return.", 403)
            line = session.execute(select(AllocationLine).where(
                AllocationLine.id == returned.allocation_line_id).with_for_update()).scalar_one_or_none()
            if line is None:
                raise AppError("WORKFLOW_INCONSISTENT", "The allocation line is unavailable.", 409)
            allocation = session.execute(select(Allocation).where(
                Allocation.id == line.allocation_id).with_for_update()).scalar_one_or_none()
            if allocation is None or allocation.status not in {"issued", "partially_returned"}:
                raise AppError("WORKFLOW_INCONSISTENT", "The active allocation is unavailable.", 409)
            _authorize(policy, actor=actor_user_id, capability="returns:verify",
                       entity_type="employee", entity_id=allocation.employee_id)
            if line.tracked_asset_id is not None:
                _authorize(policy, actor=actor_user_id, capability="assets:update",
                           entity_type="tracked_asset", entity_id=line.tracked_asset_id)
            else:
                _authorize(policy, actor=actor_user_id, capability="inventory:quantity:adjust",
                           entity_type="inventory_balance", entity_id=line.product_id)
                _authorize(policy, actor=actor_user_id, capability="inventory:quantity:adjust",
                           entity_type="location", entity_id=line.location_id)
            approval.status = decision
            approval.decided_by_id = actor_user_id
            approval.decided_at = datetime.now(timezone.utc)
            approval.decision_reason_code = reason_code
            previous_allocation_status = allocation.status
            previous_returned_quantity = Decimal(line.returned_quantity)
            if decision == "approved":
                if Decimal(line.returned_quantity) + Decimal(returned.quantity) > Decimal(line.quantity):
                    raise AppError("RETURN_EXCEEDS_ALLOCATION", "The verified return exceeds the outstanding allocation.", 409)
                if line.tracked_asset_id is not None:
                    asset = session.execute(select(TrackedAsset).where(
                        TrackedAsset.id == line.tracked_asset_id).with_for_update()).scalar_one_or_none()
                    if asset is None or asset.lifecycle_status != "allocated":
                        raise AppError("CUSTODY_MISMATCH", "The asset custody state is inconsistent.", 409)
                    asset.lifecycle_status = {"good": "available", "repair": "repair", "damaged": "damaged"}.get(
                        returned.condition, "")
                    if not asset.lifecycle_status:
                        raise AppError("RETURN_CONDITION_UNSUPPORTED", "The return condition requires review.", 409)
                else:
                    balance = session.execute(select(InventoryBalance).where(
                        InventoryBalance.product_id == line.product_id,
                        InventoryBalance.location_id == line.location_id,
                        InventoryBalance.unit == line.unit,
                    ).with_for_update()).scalar_one_or_none()
                    if balance is None or Decimal(balance.reserved) < Decimal(returned.quantity):
                        raise AppError("CUSTODY_MISMATCH", "Reserved inventory is inconsistent.", 409)
                    balance.reserved = Decimal(balance.reserved) - Decimal(returned.quantity)
                    damaged = returned.condition == "damaged"
                    if damaged:
                        balance.quarantined = Decimal(balance.quarantined) + Decimal(returned.quantity)
                    session.add(InventoryMovement(
                        product_id=line.product_id, location_id=line.location_id, unit=line.unit,
                        quantity_delta=Decimal("0") if damaged else returned.quantity,
                        reserved_delta=-Decimal(returned.quantity),
                        quarantined_delta=Decimal(returned.quantity) if damaged else Decimal("0"),
                        movement_type="quarantine" if damaged else "return", actor_user_id=actor_user_id,
                        idempotency_request_id=returned.idempotency_request_id,
                        reference_type="inventory_return", reference_id=returned.id,
                    ))
                    if damaged:
                        # Quarantined stock remains non-allocatable until an independently
                        # authorized disposition decision records its release or disposal.
                        returned.resolved_quantity = Decimal("0")
                returned.status = "verified"
                line.returned_quantity = Decimal(line.returned_quantity) + Decimal(returned.quantity)
                line.status = "returned" if line.returned_quantity == line.quantity else "partially_returned"
                remaining = session.execute(select(InventoryReturn.id).where(
                    InventoryReturn.allocation_line_id == line.id,
                    InventoryReturn.id != returned.id,
                    InventoryReturn.status == "pending",
                )).first()
                if line.status == "returned" and remaining is None:
                    allocation.status = "returned"
                else:
                    allocation.status = "partially_returned" if line.status == "partially_returned" else "issued"
            else:
                returned.status = "rejected"
            audit_writer(session, AuditEventInput(
                actor_user_id=actor_user_id, action="inventory.return_decided",
                entity_type="inventory_return", entity_id=returned.id,
                metadata={"changed_fields": ["approval_status", "allocation_status", "returned_quantity"]},
                previous_values={"approval_status": "pending",
                                 "allocation_status": previous_allocation_status,
                                 "returned_quantity": previous_returned_quantity},
                updated_values={"approval_status": decision,
                                "allocation_status": allocation.status,
                                "returned_quantity": Decimal(line.returned_quantity)},
            ))
            session.flush()
    except AppError:
        raise
    except IntegrityError:
        raise AppError("INVENTORY_CONFLICT", "The return conflicts with current inventory.", 409) from None
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The return decision could not be recorded.", 503) from None


def allocation_history(session: Session, *, actor_user_id: UUID,
                       policy: InventoryWritePolicy | None, limit: int = 50,
                       offset: int = 0) -> list[AllocationRead]:
    _authorize(policy, actor=actor_user_id, capability="allocations:read",
               entity_type="allocation_history")
    if not 1 <= limit <= 100 or not 0 <= offset <= 10000:
        raise AppError("INVALID_PAGE", "The allocation page is invalid.", 422)
    try:
        rows = session.execute(select(Allocation, AllocationLine).join(
            AllocationLine, AllocationLine.allocation_id == Allocation.id
        ).order_by(Allocation.created_at.desc(), Allocation.id).limit(limit).offset(offset)).all()
        result: list[AllocationRead] = []
        for allocation, line in rows:
            _authorize(policy, actor=actor_user_id, capability="allocations:read",
                       entity_type="employee", entity_id=allocation.employee_id)
            result.append(AllocationRead(
            id=allocation.id, employee_id=allocation.employee_id, status=allocation.status,
            line_id=line.id, tracked_asset_id=line.tracked_asset_id, product_id=line.product_id,
            location_id=line.location_id, unit=line.unit, quantity=line.quantity,
            returned_quantity=line.returned_quantity, line_status=line.status,
            created_at=allocation.created_at,
            ))
        return result
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "Allocation history is unavailable.", 503) from None


def return_history(session: Session, *, actor_user_id: UUID,
                   policy: InventoryWritePolicy | None, limit: int = 50,
                   offset: int = 0) -> list[ReturnRead]:
    _authorize(policy, actor=actor_user_id, capability="returns:read",
               entity_type="return_history")
    if not 1 <= limit <= 100 or not 0 <= offset <= 10000:
        raise AppError("INVALID_PAGE", "The return page is invalid.", 422)
    try:
        rows = session.execute(select(InventoryReturn).order_by(
            InventoryReturn.created_at.desc(), InventoryReturn.id).limit(limit).offset(offset)).scalars()
        result: list[ReturnRead] = []
        for row in rows:
            _authorize(policy, actor=actor_user_id, capability="returns:read",
                       entity_type="inventory_return", entity_id=row.id)
            result.append(ReturnRead(id=row.id, allocation_line_id=row.allocation_line_id,
                                     quantity=row.quantity, condition=row.condition, status=row.status,
                                     recorded_by_id=row.recorded_by_id, created_at=row.created_at))
        return result
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "Return history is unavailable.", 503) from None
