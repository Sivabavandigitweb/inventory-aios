"""Policy-gated repair, disposal and employee exit-clearance operations."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    Allocation,
    AllocationLine,
    AssetRepair,
    DisposalRequest,
    Employee,
    EmployeeExitClearance,
    TrackedAsset,
    WorkflowApproval,
)
from app.services.audit import AuditEventInput, write_audit_event
from app.services.inventory_writes import (
    InventoryWritePolicy,
    _authorize,
    _idempotent,
    _self_approval_allowed,
)
from app.services.workflows import validate_asset_transition

APPROVED_DISPOSAL_REASONS = {
    "damaged_beyond_repair": "Damaged beyond repair",
    "obsolete": "Obsolete",
    "end_of_useful_life": "End of useful life",
    "uneconomical_repair": "Uneconomical repair",
}


def _approval(session: Session, entity_type: str, entity_id: UUID) -> WorkflowApproval | None:
    return session.execute(select(WorkflowApproval).where(
        WorkflowApproval.entity_type == entity_type,
        WorkflowApproval.entity_id == entity_id,
        WorkflowApproval.status == "pending").with_for_update()).scalar_one_or_none()


def _configured_policy_value(policy: object | None, method_name: str, value: object) -> None:
    checker = getattr(policy, method_name, None) if policy is not None else None
    try:
        allowed = checker(value) if callable(checker) else False
    except Exception:
        allowed = False
    if allowed is not True:
        raise AppError("WORKFLOW_POLICY_UNAVAILABLE", "The required company workflow policy is not configured.", 503)


def request_repair(session: Session, *, asset_id: UUID, actor_user_id: UUID,
                   issue_details: str, provider: str | None,
                   idempotency_key: str, policy: InventoryWritePolicy | None) -> UUID:
    if not issue_details.strip():
        raise AppError("INVALID_REPAIR", "Repair issue details are required.", 422)
    _authorize(policy, actor=actor_user_id, capability="repairs:report",
               entity_type="tracked_asset", entity_id=asset_id)
    try:
        def create(request_uuid: UUID) -> tuple[UUID, str]:
            with session.begin_nested():
                asset = session.execute(select(TrackedAsset).where(
                TrackedAsset.id == asset_id).with_for_update()).scalar_one_or_none()
                if asset is None or asset.lifecycle_status not in {"available", "damaged"}:
                    raise AppError("REPAIR_UNAVAILABLE", "The asset is not eligible for a repair case.", 409)
                if session.execute(select(AllocationLine.id).where(
                    AllocationLine.tracked_asset_id == asset_id,
                    AllocationLine.status.in_(("pending", "active", "partially_returned")),
                )).first():
                    raise AppError("REPAIR_UNAVAILABLE", "The asset has unresolved allocation custody.", 409)
                if session.execute(select(DisposalRequest.id).where(
                    DisposalRequest.tracked_asset_id == asset_id,
                    DisposalRequest.status.in_(("pending", "approved")))).first():
                    raise AppError("REPAIR_UNAVAILABLE", "The asset is under disposal review.", 409)
                previous_lifecycle = asset.lifecycle_status
                if asset.lifecycle_status == "available":
                    validate_asset_transition(asset.lifecycle_status, "damaged")
                    asset.lifecycle_status = "damaged"
                repair = AssetRepair(tracked_asset_id=asset_id, status="reported",
                reported_by_id=actor_user_id, issue_details=issue_details.strip(),
                repair_provider=provider.strip() if provider else None)
                session.add(repair)
                session.flush()
                session.add(WorkflowApproval(entity_type="repair", entity_id=repair.id,
                required_capability="approvals:decide:repair", status="pending",
                requested_by_id=actor_user_id))
                write_audit_event(session, AuditEventInput(actor_user_id=actor_user_id,
                action="asset.repair_requested", entity_type="asset_repair", entity_id=repair.id,
                metadata={"changed_fields": ["repair_status", "lifecycle_status"]},
                previous_values={"lifecycle_status": previous_lifecycle},
                updated_values={"repair_status": "reported", "lifecycle_status": "damaged"}))
                session.flush()
                return repair.id, "pending_approval"
        result = _idempotent(session, actor=actor_user_id, scope="asset.repair.request",
            key=idempotency_key, payload={"asset_id": str(asset_id), "issue_details": issue_details,
            "provider": provider}, create=create)
        return result.id
    except AppError:
        raise
    except IntegrityError:
        raise AppError("REPAIR_ALREADY_OPEN", "An open repair case already exists for this asset.", 409) from None
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The repair case could not be opened.", 503) from None


def decide_repair(session: Session, *, repair_id: UUID, actor_user_id: UUID,
                  decision: str, reason_code: str | None,
                  policy: InventoryWritePolicy | None) -> None:
    if decision not in {"approved", "rejected"}:
        raise AppError("INVALID_DECISION", "The approval decision is invalid.", 422)
    _authorize(policy, actor=actor_user_id, capability="approvals:decide:repair",
               entity_type="asset_repair", entity_id=repair_id)
    try:
        with session.begin_nested():
            repair = session.execute(select(AssetRepair).where(
                AssetRepair.id == repair_id).with_for_update()).scalar_one_or_none()
            approval = _approval(session, "repair", repair_id)
            if repair is None or repair.status != "reported" or approval is None:
                raise AppError("APPROVAL_UNAVAILABLE", "A pending repair approval was not found.", 409)
            if repair.reported_by_id == actor_user_id and not _self_approval_allowed(policy, "repair"):
                raise AppError("SELF_APPROVAL_DENIED", "The repair requester cannot approve their request.", 403)
            approval.status = decision
            approval.decided_by_id = actor_user_id
            approval.decided_at = datetime.now(timezone.utc)
            approval.decision_reason_code = reason_code
            if decision == "approved":
                repair.status = "in_progress"
                asset = session.execute(select(TrackedAsset).where(
                    TrackedAsset.id == repair.tracked_asset_id).with_for_update()).scalar_one_or_none()
                if asset is None or asset.lifecycle_status != "damaged":
                    raise AppError("WORKFLOW_INCONSISTENT", "The repair asset state is unavailable.", 409)
                validate_asset_transition("damaged", "repair")
                asset.lifecycle_status = "repair"
            else:
                repair.status = "cancelled"
            write_audit_event(session, AuditEventInput(actor_user_id=actor_user_id,
                action="asset.repair_decided", entity_type="asset_repair", entity_id=repair_id,
                metadata={"changed_fields": ["repair_status", "approval_status"]},
                previous_values={"repair_status": "reported", "approval_status": "pending"},
                updated_values={"repair_status": repair.status, "approval_status": decision}))
            session.flush()
    except AppError:
        raise
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The repair decision could not be recorded.", 503) from None


def complete_repair(session: Session, *, repair_id: UUID, actor_user_id: UUID,
                    condition: str, notes: str | None, cost_amount: float | None,
                    cost_currency: str | None, policy: InventoryWritePolicy | None) -> None:
    if condition not in {"good", "damaged"} or (cost_amount is None) != (cost_currency is None):
        raise AppError("INVALID_REPAIR_COMPLETION", "Repair completion values are invalid.", 422)
    if cost_currency is not None:
        _configured_policy_value(policy, "allows_repair_cost_currency", cost_currency.upper())
    _authorize(policy, actor=actor_user_id, capability="repairs:update",
               entity_type="asset_repair", entity_id=repair_id)
    try:
        with session.begin_nested():
            repair = session.execute(select(AssetRepair).where(
                AssetRepair.id == repair_id).with_for_update()).scalar_one_or_none()
            if repair is None or repair.status != "in_progress":
                raise AppError("REPAIR_UNAVAILABLE", "An active repair case was not found.", 409)
            approval = session.execute(select(WorkflowApproval).where(
                WorkflowApproval.entity_type == "repair", WorkflowApproval.entity_id == repair_id,
                WorkflowApproval.status == "approved").with_for_update()).scalar_one_or_none()
            if approval is None or (approval.decided_by_id == repair.reported_by_id
                                    and not _self_approval_allowed(policy, "repair")):
                raise AppError("APPROVAL_REQUIRED", "A current independent repair approval is required.", 403)
            asset = session.execute(select(TrackedAsset).where(
                TrackedAsset.id == repair.tracked_asset_id).with_for_update()).scalar_one_or_none()
            if asset is None or asset.lifecycle_status != "repair":
                raise AppError("WORKFLOW_INCONSISTENT", "The asset is not in repair custody.", 409)
            target = "available" if condition == "good" else "damaged"
            validate_asset_transition("repair", target)
            before = asset.lifecycle_status
            asset.lifecycle_status = target
            repair.status = "completed"
            repair.closed_at = datetime.now(timezone.utc)
            repair.completion_condition = condition
            repair.completion_notes = notes.strip() if notes else None
            repair.cost_amount = cost_amount
            repair.cost_currency = cost_currency.upper() if cost_currency else None
            write_audit_event(session, AuditEventInput(actor_user_id=actor_user_id,
                action="asset.repair_completed", entity_type="asset_repair", entity_id=repair_id,
                metadata={"changed_fields": ["repair_status", "lifecycle_status", "condition"]},
                previous_values={"repair_status": "in_progress", "lifecycle_status": before},
                updated_values={"repair_status": "completed", "lifecycle_status": target, "condition": condition}))
            session.flush()
    except AppError:
        raise
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "Repair completion could not be recorded.", 503) from None


def request_disposal(session: Session, *, asset_id: UUID, actor_user_id: UUID,
                     reason_code: str, condition: str | None,
                     idempotency_key: str, policy: InventoryWritePolicy | None) -> UUID:
    if not isinstance(reason_code, str) or reason_code.strip() not in APPROVED_DISPOSAL_REASONS:
        raise AppError("INVALID_DISPOSAL", "The disposal reason is invalid.", 422)
    reason_code = reason_code.strip()
    _configured_policy_value(policy, "allows_disposal_reason", reason_code)
    _authorize(policy, actor=actor_user_id, capability="disposals:request",
               entity_type="tracked_asset", entity_id=asset_id)
    try:
        def create(request_uuid: UUID) -> tuple[UUID, str]:
            asset = session.execute(select(TrackedAsset).where(
                TrackedAsset.id == asset_id).with_for_update()).scalar_one_or_none()
            if asset is None or asset.lifecycle_status not in {"available", "damaged"}:
                raise AppError("DISPOSAL_UNAVAILABLE", "The asset is not eligible for disposal review.", 409)
            if session.execute(select(AllocationLine.id).where(
                AllocationLine.tracked_asset_id == asset_id,
                AllocationLine.status.in_(("pending", "active", "partially_returned")),
            )).first():
                raise AppError("DISPOSAL_UNAVAILABLE", "The asset has unresolved allocation custody.", 409)
            active_repair = session.execute(select(AssetRepair.id).where(
                AssetRepair.tracked_asset_id == asset_id,
                AssetRepair.status.in_(("reported", "in_progress")))).first()
            if active_repair:
                raise AppError("DISPOSAL_UNAVAILABLE", "An unresolved repair case exists.", 409)
            request = DisposalRequest(tracked_asset_id=asset_id, quantity=1, status="pending",
                requested_by_id=actor_user_id, reason_code=reason_code.strip(), condition=condition,
                idempotency_request_id=request_uuid)
            session.add(request)
            session.flush()
            session.add(WorkflowApproval(entity_type="disposal", entity_id=request.id,
                required_capability="approvals:decide:disposal", status="pending",
                requested_by_id=actor_user_id))
            write_audit_event(session, AuditEventInput(actor_user_id=actor_user_id,
                action="asset.disposal_requested", entity_type="disposal_request", entity_id=request.id,
                metadata={"changed_fields": ["disposal_status"]},
                updated_values={"disposal_status": "pending"}))
            return request.id, "pending_approval"
        result = _idempotent(session, actor=actor_user_id, scope="asset.disposal.request",
            key=idempotency_key, payload={"asset_id": str(asset_id), "reason_code": reason_code,
            "condition": condition}, create=create)
        return result.id
    except AppError:
        raise


def decide_disposal(session: Session, *, request_id: UUID, actor_user_id: UUID,
                    decision: str, reason_code: str | None,
                    policy: InventoryWritePolicy | None) -> None:
    if decision not in {"approved", "rejected"}:
        raise AppError("INVALID_DECISION", "The approval decision is invalid.", 422)
    _authorize(policy, actor=actor_user_id, capability="approvals:decide:disposal",
               entity_type="disposal_request", entity_id=request_id)
    request = session.execute(select(DisposalRequest).where(
        DisposalRequest.id == request_id).with_for_update()).scalar_one_or_none()
    approval = _approval(session, "disposal", request_id)
    if request is None or request.status != "pending" or approval is None:
        raise AppError("APPROVAL_UNAVAILABLE", "A pending disposal approval was not found.", 409)
    if request.requested_by_id == actor_user_id and not _self_approval_allowed(policy, "asset_disposal"):
        raise AppError("SELF_APPROVAL_DENIED", "The requester cannot decide their own disposal.", 403)
    approval.status = decision
    approval.decided_by_id = actor_user_id
    approval.decided_at = datetime.now(timezone.utc)
    approval.decision_reason_code = reason_code
    request.status = decision
    write_audit_event(session, AuditEventInput(actor_user_id=actor_user_id,
        action="asset.disposal_decided", entity_type="disposal_request", entity_id=request_id,
        metadata={"changed_fields": ["disposal_status", "approval_status"]},
        previous_values={"disposal_status": "pending", "approval_status": "pending"},
        updated_values={"disposal_status": decision, "approval_status": decision}))
    session.flush()


def finalize_disposal(session: Session, *, request_id: UUID, actor_user_id: UUID,
                      policy: InventoryWritePolicy | None) -> None:
    _authorize(policy, actor=actor_user_id, capability="disposals:finalize",
               entity_type="disposal_request", entity_id=request_id)
    try:
        with session.begin_nested():
            request = session.execute(select(DisposalRequest).where(
                DisposalRequest.id == request_id).with_for_update()).scalar_one_or_none()
            approval = session.execute(select(WorkflowApproval).where(
                WorkflowApproval.entity_type == "disposal", WorkflowApproval.entity_id == request_id,
                WorkflowApproval.status == "approved").with_for_update()).scalar_one_or_none()
            if request is None or request.status != "approved" or approval is None:
                raise AppError("APPROVAL_REQUIRED", "An approved disposal request is required.", 403)
            if approval.decided_by_id == request.requested_by_id and not _self_approval_allowed(policy, "asset_disposal"):
                raise AppError("SELF_APPROVAL_DENIED", "The requester cannot approve their disposal.", 403)
            if policy is None or policy.approval_satisfied(action="asset_disposal",
                    entity_id=request_id, actor_user_id=actor_user_id) is not True:
                raise AppError("APPROVAL_REQUIRED", "Current disposal approval is unavailable.", 403)
            if request.tracked_asset_id is None:
                raise AppError("DISPOSAL_UNAVAILABLE", "Quantity disposal requires an approved quarantine disposition.", 409)
            asset = session.execute(select(TrackedAsset).where(
                TrackedAsset.id == request.tracked_asset_id).with_for_update()).scalar_one_or_none()
            if asset is None or asset.lifecycle_status not in {"available", "damaged"}:
                raise AppError("DISPOSAL_UNAVAILABLE", "The asset has unresolved custody or lifecycle state.", 409)
            if session.execute(select(AllocationLine.id).where(
                AllocationLine.tracked_asset_id == asset.id,
                AllocationLine.status.in_(("pending", "active", "partially_returned")),
            )).first():
                raise AppError("DISPOSAL_UNAVAILABLE", "The asset has an unresolved allocation.", 409)
            if session.execute(select(AssetRepair.id).where(
                AssetRepair.tracked_asset_id == asset.id,
                AssetRepair.status.in_(("reported", "in_progress")),
            )).first():
                raise AppError("DISPOSAL_UNAVAILABLE", "The asset has an unresolved repair case.", 409)
            validate_asset_transition(asset.lifecycle_status, "disposed")
            previous = asset.lifecycle_status
            asset.lifecycle_status = "disposed"
            request.status = "completed"
            request.completed_by_id = actor_user_id
            request.completed_at = datetime.now(timezone.utc)
            write_audit_event(session, AuditEventInput(actor_user_id=actor_user_id,
                action="asset.disposal_completed", entity_type="tracked_asset", entity_id=asset.id,
                metadata={"changed_fields": ["lifecycle_status", "disposal_status"]},
                previous_values={"lifecycle_status": previous, "disposal_status": "approved"},
                updated_values={"lifecycle_status": "disposed", "disposal_status": "completed"}))
            session.flush()
    except AppError:
        raise
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The disposal could not be finalized.", 503) from None


def outstanding_exit_items(session: Session, *, employee_id: UUID) -> list[dict[str, object]]:
    rows = session.execute(select(Allocation, AllocationLine).join(
        AllocationLine, AllocationLine.allocation_id == Allocation.id).where(
            Allocation.employee_id == employee_id,
            AllocationLine.status.in_(("pending", "active", "partially_returned"))
        ).order_by(Allocation.created_at, AllocationLine.id)).all()
    return [{"allocation_id": allocation.id, "line_id": line.id,
             "outstanding_quantity": line.quantity - line.returned_quantity,
             "tracked_asset_id": line.tracked_asset_id, "product_id": line.product_id,
             "unit": line.unit} for allocation, line in rows]


def open_exit_clearance(session: Session, *, employee_id: UUID, actor_user_id: UUID,
                        policy: InventoryWritePolicy | None) -> UUID:
    _authorize(policy, actor=actor_user_id, capability="exit_clearance:open",
               entity_type="employee", entity_id=employee_id)
    employee = session.execute(select(Employee).where(Employee.id == employee_id)
                               .with_for_update()).scalar_one_or_none()
    if employee is None:
        raise AppError("NOT_FOUND", "Employee was not found.", 404)
    clearance = EmployeeExitClearance(employee_id=employee_id, opened_by_id=actor_user_id,
                                      status="in_progress", verification_status="unverified")
    session.add(clearance)
    session.flush()
    session.add(WorkflowApproval(entity_type="exit_clearance", entity_id=clearance.id,
        required_capability="approvals:decide:exit_clearance", status="pending",
        requested_by_id=actor_user_id))
    write_audit_event(session, AuditEventInput(actor_user_id=actor_user_id,
        action="exit_clearance.opened", entity_type="employee_exit_clearance", entity_id=clearance.id,
        metadata={"changed_fields": ["clearance_status"]},
        updated_values={"clearance_status": "in_progress"}))
    session.flush()
    return clearance.id


def verify_exit_clearance(session: Session, *, clearance_id: UUID, actor_user_id: UUID,
                          policy: InventoryWritePolicy | None) -> None:
    _authorize(policy, actor=actor_user_id, capability="approvals:decide:exit_clearance",
               entity_type="employee_exit_clearance", entity_id=clearance_id)
    clearance = session.execute(select(EmployeeExitClearance).where(
        EmployeeExitClearance.id == clearance_id).with_for_update()).scalar_one_or_none()
    if clearance is None or clearance.status not in {"pending", "in_progress"}:
        raise AppError("CLEARANCE_UNAVAILABLE", "An open exit clearance was not found.", 409)
    if clearance.opened_by_id == actor_user_id and not _self_approval_allowed(policy, "exit_clearance"):
        raise AppError("SELF_APPROVAL_DENIED", "The case opener cannot verify the clearance.", 403)
    approval = _approval(session, "exit_clearance", clearance_id)
    if approval is None or (approval.requested_by_id == actor_user_id
                            and not _self_approval_allowed(policy, "exit_clearance")):
        raise AppError("APPROVAL_REQUIRED", "An independent clearance approval is required.", 403)
    if outstanding_exit_items(session, employee_id=clearance.employee_id):
        raise AppError("EXIT_CLEARANCE_INCOMPLETE", "Outstanding inventory prevents verification.", 409)
    previous_verification = clearance.verification_status
    approval.status = "approved"
    approval.decided_by_id = actor_user_id
    approval.decided_at = datetime.now(timezone.utc)
    clearance.verification_status = "verified"
    write_audit_event(session, AuditEventInput(actor_user_id=actor_user_id,
        action="exit_clearance.verified", entity_type="employee_exit_clearance", entity_id=clearance_id,
        metadata={"changed_fields": ["verification_status"]},
        previous_values={"verification_status": previous_verification},
        updated_values={"verification_status": "verified"}))
    session.flush()


def decide_exit_clearance(session: Session, *, clearance_id: UUID, actor_user_id: UUID,
                          decision: str, policy: InventoryWritePolicy | None) -> None:
    if decision not in {"approved", "rejected"}:
        raise AppError("INVALID_DECISION", "The approval decision is invalid.", 422)
    _authorize(policy, actor=actor_user_id, capability="approvals:decide:exit_clearance",
               entity_type="employee_exit_clearance", entity_id=clearance_id)
    clearance = session.execute(select(EmployeeExitClearance).where(
        EmployeeExitClearance.id == clearance_id).with_for_update()).scalar_one_or_none()
    approval = _approval(session, "exit_clearance", clearance_id)
    if clearance is None or clearance.status not in {"pending", "in_progress"} or approval is None:
        raise AppError("APPROVAL_UNAVAILABLE", "A pending exit clearance decision was not found.", 409)
    if approval.requested_by_id == actor_user_id and not _self_approval_allowed(policy, "exit_clearance"):
        raise AppError("SELF_APPROVAL_DENIED", "The clearance requester cannot decide their own request.", 403)
    previous = clearance.verification_status
    if decision == "approved":
        if outstanding_exit_items(session, employee_id=clearance.employee_id):
            raise AppError("EXIT_CLEARANCE_INCOMPLETE", "Outstanding inventory prevents approval.", 409)
        clearance.verification_status = "verified"
    else:
        clearance.verification_status = "exceptions"
    approval.status = decision
    approval.decided_by_id = actor_user_id
    approval.decided_at = datetime.now(timezone.utc)
    write_audit_event(session, AuditEventInput(actor_user_id=actor_user_id,
        action="exit_clearance.decided", entity_type="employee_exit_clearance", entity_id=clearance_id,
        metadata={"changed_fields": ["approval_status", "verification_status"]},
        previous_values={"approval_status": "pending", "verification_status": previous},
        updated_values={"approval_status": decision, "verification_status": clearance.verification_status}))
    session.flush()


def list_open_clearances(session: Session, *, policy: InventoryWritePolicy | None,
                         actor_user_id: UUID) -> list[dict[str, object]]:
    _authorize(policy, actor=actor_user_id, capability="exit_clearance:read",
               entity_type="employee_exit_clearance")
    rows = session.execute(select(EmployeeExitClearance).order_by(
        EmployeeExitClearance.created_at.desc())).scalars().all()
    return [{"id": row.id, "employee_id": row.employee_id, "status": row.status,
             "verification_status": row.verification_status,
             "outstanding": outstanding_exit_items(session, employee_id=row.employee_id)} for row in rows]


def list_repairs(session: Session, *, actor_user_id: UUID,
                 policy: InventoryWritePolicy | None) -> list[dict[str, object]]:
    _authorize(policy, actor=actor_user_id, capability="repairs:read", entity_type="asset_repair")
    rows = session.execute(select(AssetRepair).order_by(AssetRepair.opened_at.desc())).scalars().all()
    return [{"id": row.id, "tracked_asset_id": row.tracked_asset_id, "status": row.status,
             "issue_details": row.issue_details, "repair_provider": row.repair_provider,
             "opened_at": row.opened_at, "closed_at": row.closed_at,
             "completion_condition": row.completion_condition, "cost_amount": row.cost_amount,
             "cost_currency": row.cost_currency} for row in rows]


def list_disposals(session: Session, *, actor_user_id: UUID,
                   policy: InventoryWritePolicy | None) -> list[dict[str, object]]:
    _authorize(policy, actor=actor_user_id, capability="disposals:read", entity_type="disposal_request")
    rows = session.execute(select(DisposalRequest).order_by(DisposalRequest.created_at.desc())).scalars().all()
    return [{"id": row.id, "tracked_asset_id": row.tracked_asset_id,
             "status": row.status, "reason_code": row.reason_code, "condition": row.condition,
             "requested_by_id": row.requested_by_id, "completed_by_id": row.completed_by_id,
             "completed_at": row.completed_at} for row in rows]


def cancel_exit_clearance(session: Session, *, clearance_id: UUID, actor_user_id: UUID,
                          policy: InventoryWritePolicy | None) -> None:
    _authorize(policy, actor=actor_user_id, capability="exit_clearance:cancel",
               entity_type="employee_exit_clearance", entity_id=clearance_id)
    if policy is None:
        raise AppError("WORKFLOW_UNAVAILABLE", "Clearance cancellation policy is unavailable.", 503)
    try:
        if policy.approval_satisfied(action="exit_clearance_cancellation",
                entity_id=clearance_id, actor_user_id=actor_user_id) is not True:
            raise AppError("APPROVAL_REQUIRED", "Clearance cancellation is not authorized.", 403)
        clearance = session.execute(select(EmployeeExitClearance).where(
            EmployeeExitClearance.id == clearance_id).with_for_update()).scalar_one_or_none()
        if clearance is None or clearance.status not in {"pending", "in_progress"}:
            raise AppError("CLEARANCE_UNAVAILABLE", "An open clearance was not found.", 409)
        approval = _approval(session, "exit_clearance", clearance_id)
        if approval is not None:
            approval.status = "cancelled"
        clearance.status = "cancelled"
        write_audit_event(session, AuditEventInput(actor_user_id=actor_user_id,
            action="exit_clearance.cancelled", entity_type="employee_exit_clearance", entity_id=clearance_id,
            metadata={"changed_fields": ["clearance_status"]},
            previous_values={"clearance_status": "in_progress"},
            updated_values={"clearance_status": "cancelled"}))
        session.flush()
    except AppError:
        raise
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The clearance could not be cancelled.", 503) from None
