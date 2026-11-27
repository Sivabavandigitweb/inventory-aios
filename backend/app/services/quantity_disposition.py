"""Approval-gated quarantine transitions for damaged quantity returns."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    AllocationLine,
    InventoryBalance,
    InventoryMovement,
    InventoryReturn,
    QuantityDispositionRequest,
    WorkflowApproval,
)
from app.services.audit import AuditEventInput, write_audit_event
from app.services.inventory_writes import (
    InventoryWritePolicy,
    _authorize,
    _idempotent,
    _self_approval_allowed,
)


def request_quantity_disposition(
    session: Session, *, return_id: UUID, actor_user_id: UUID, quantity: Decimal,
    disposition: str, idempotency_key: str, policy: InventoryWritePolicy | None,
) -> UUID:
    if disposition not in {"release", "dispose"} or quantity <= 0:
        raise AppError("INVALID_DISPOSITION", "The requested disposition is invalid.", 422)
    _authorize(policy, actor=actor_user_id, capability="inventory:quantity:disposition:request",
               entity_type="inventory_return", entity_id=return_id)
    def create(request_id: UUID) -> tuple[UUID, str]:
        returned = session.execute(select(InventoryReturn).where(
            InventoryReturn.id == return_id).with_for_update()).scalar_one_or_none()
        if returned is None or returned.status != "verified" or returned.condition != "damaged":
            raise AppError("DISPOSITION_UNAVAILABLE", "A verified damaged quantity return is required.", 409)
        line = session.execute(select(AllocationLine).where(
            AllocationLine.id == returned.allocation_line_id).with_for_update()).scalar_one_or_none()
        if line is None or line.product_id is None or line.location_id is None or line.unit is None:
            raise AppError("WORKFLOW_INCONSISTENT", "The quantity return inventory reference is unavailable.", 409)
        already_requested = session.scalar(select(func.coalesce(func.sum(
            QuantityDispositionRequest.quantity), 0)).where(
                QuantityDispositionRequest.inventory_return_id == return_id,
                QuantityDispositionRequest.status.in_(("pending", "approved", "completed")),
        )) or Decimal("0")
        unresolved = session.scalar(select(func.coalesce(func.sum(
            QuantityDispositionRequest.quantity), 0)).where(
                QuantityDispositionRequest.inventory_return_id == return_id,
                QuantityDispositionRequest.status.in_(("pending", "approved")),
        )) or Decimal("0")
        if Decimal(already_requested) + quantity > Decimal(returned.quantity):
            raise AppError("DISPOSITION_EXCEEDS_RETURN", "The disposition exceeds the damaged return quantity.", 409)
        balance = session.execute(select(InventoryBalance).where(
            InventoryBalance.product_id == line.product_id,
            InventoryBalance.location_id == line.location_id,
            InventoryBalance.unit == line.unit,
        ).with_for_update()).scalar_one_or_none()
        if balance is None or Decimal(balance.quarantined) < Decimal(unresolved) + quantity:
            raise AppError("QUARANTINE_INCONSISTENT", "The quarantined balance is unavailable.", 409)
        request = QuantityDispositionRequest(
            inventory_return_id=return_id, quantity=quantity, disposition=disposition,
            status="pending", requested_by_id=actor_user_id,
            idempotency_request_id=request_id,
        )
        session.add(request)
        session.flush()
        session.add(WorkflowApproval(
            entity_type="quantity_disposition", entity_id=request.id,
            required_capability="approvals:decide:quantity_disposition",
            status="pending", requested_by_id=actor_user_id,
        ))
        return request.id, "pending_approval"
    result = _idempotent(session, actor=actor_user_id, scope="inventory.quantity_disposition.request",
                         key=idempotency_key, payload={"return_id": str(return_id),
                         "quantity": str(quantity), "disposition": disposition}, create=create)
    return result.id


def decide_quantity_disposition(
    session: Session, *, request_id: UUID, actor_user_id: UUID, decision: str,
    reason_code: str | None, policy: InventoryWritePolicy | None,
) -> None:
    if decision not in {"approved", "rejected"}:
        raise AppError("INVALID_DECISION", "The approval decision is invalid.", 422)
    _authorize(policy, actor=actor_user_id, capability="approvals:decide:quantity_disposition",
               entity_type="quantity_disposition", entity_id=request_id)
    try:
        with session.begin_nested():
            request = session.execute(select(QuantityDispositionRequest).where(
                QuantityDispositionRequest.id == request_id).with_for_update()).scalar_one_or_none()
            approval = session.execute(select(WorkflowApproval).where(
                WorkflowApproval.entity_type == "quantity_disposition",
                WorkflowApproval.entity_id == request_id,
                WorkflowApproval.status == "pending").with_for_update()).scalar_one_or_none()
            if request is None or request.status != "pending" or approval is None:
                raise AppError("APPROVAL_UNAVAILABLE", "A pending disposition approval was not found.", 409)
            if request.requested_by_id == actor_user_id and not _self_approval_allowed(policy, "quantity_disposition"):
                raise AppError("SELF_APPROVAL_DENIED", "The requester cannot decide their own disposition.", 403)
            approval.status = decision
            approval.decided_by_id = actor_user_id
            approval.decided_at = datetime.now(timezone.utc)
            approval.decision_reason_code = reason_code
            request.status = decision
            write_audit_event(session, AuditEventInput(
                actor_user_id=actor_user_id, action="inventory.quantity_disposition_decided",
                entity_type="quantity_disposition_request", entity_id=request_id,
                metadata={"changed_fields": ["approval_status"]},
                previous_values={"approval_status": "pending"},
                updated_values={"approval_status": decision},
            ))
            session.flush()
    except AppError:
        raise
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The disposition decision could not be recorded.", 503) from None


def finalize_quantity_disposition(
    session: Session, *, request_id: UUID, actor_user_id: UUID,
    policy: InventoryWritePolicy | None,
) -> None:
    _authorize(policy, actor=actor_user_id, capability="inventory:quantity:disposition:decide",
               entity_type="quantity_disposition", entity_id=request_id)
    try:
        with session.begin_nested():
            request = session.execute(select(QuantityDispositionRequest).where(
                QuantityDispositionRequest.id == request_id).with_for_update()).scalar_one_or_none()
            approval = session.execute(select(WorkflowApproval).where(
                WorkflowApproval.entity_type == "quantity_disposition",
                WorkflowApproval.entity_id == request_id,
                WorkflowApproval.status == "approved").with_for_update()).scalar_one_or_none()
            if request is None or request.status != "approved" or approval is None:
                raise AppError("APPROVAL_REQUIRED", "An approved disposition is required.", 403)
            if approval.decided_by_id == request.requested_by_id and not _self_approval_allowed(policy, "quantity_disposition"):
                raise AppError("SELF_APPROVAL_DENIED", "The requester cannot approve their own disposition.", 403)
            if policy is None or policy.approval_satisfied(
                action="quantity_disposition", entity_id=request_id,
                actor_user_id=actor_user_id) is not True:
                raise AppError("APPROVAL_REQUIRED", "Current disposition approval is unavailable.", 403)
            returned = session.execute(select(InventoryReturn).where(
                InventoryReturn.id == request.inventory_return_id).with_for_update()).scalar_one_or_none()
            line = session.execute(select(AllocationLine).where(
                AllocationLine.id == returned.allocation_line_id).with_for_update()).scalar_one_or_none() if returned else None
            if not returned or not line or not line.product_id or not line.location_id or not line.unit:
                raise AppError("WORKFLOW_INCONSISTENT", "The disposition inventory reference is unavailable.", 409)
            balance = session.execute(select(InventoryBalance).where(
                InventoryBalance.product_id == line.product_id,
                InventoryBalance.location_id == line.location_id,
                InventoryBalance.unit == line.unit).with_for_update()).scalar_one_or_none()
            quantity = Decimal(request.quantity)
            if balance is None or Decimal(balance.quarantined) < quantity:
                raise AppError("QUARANTINE_INCONSISTENT", "The quarantined balance is insufficient.", 409)
            before_on_hand = Decimal(balance.on_hand)
            before_quarantined = Decimal(balance.quarantined)
            balance.quarantined = Decimal(balance.quarantined) - quantity
            on_hand_delta = Decimal("0")
            if request.disposition == "release":
                movement_type = "quarantine_release"
            else:
                balance.on_hand = Decimal(balance.on_hand) - quantity
                on_hand_delta = -quantity
                movement_type = "quarantine_disposal"
            returned.resolved_quantity = Decimal(returned.resolved_quantity) + quantity
            request.status = "completed"
            session.add(InventoryMovement(
                product_id=line.product_id, location_id=line.location_id, unit=line.unit,
                quantity_delta=quantity if request.disposition == "release" else Decimal("0"),
                on_hand_delta=on_hand_delta, quarantined_delta=-quantity,
                movement_type=movement_type, actor_user_id=actor_user_id,
                idempotency_request_id=request.idempotency_request_id,
                reference_type="quantity_disposition", reference_id=request.id,
            ))
            write_audit_event(session, AuditEventInput(
                actor_user_id=actor_user_id, action="inventory.quantity_disposition_completed",
                entity_type="quantity_disposition_request", entity_id=request_id,
                metadata={"changed_fields": ["on_hand", "quarantined", "disposition_status"]},
                previous_values={"on_hand": before_on_hand, "quarantined": before_quarantined,
                                 "disposition_status": "approved"},
                updated_values={"on_hand": balance.on_hand, "quarantined": balance.quarantined,
                                "disposition_status": "completed"},
            ))
            session.flush()
    except AppError:
        raise
    except IntegrityError:
        raise AppError("INVENTORY_CONFLICT", "The disposition conflicts with current inventory.", 409) from None
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The disposition could not be finalized.", 503) from None
