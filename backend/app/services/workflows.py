"""Fail-closed transaction helpers; never registered as operational write routes."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models import (
    Allocation,
    AllocationLine,
    EmployeeExitClearance,
    TrackedAsset,
    WorkflowApproval,
)
from app.services.audit import AuditEventInput, write_audit_event
from app.services.inventory_writes import _self_approval_allowed


class WorkflowPolicy(Protocol):
    def authorize(self, *, actor_user_id: UUID, capability: str, entity_type: str, entity_id: UUID) -> bool: ...
    def approval_satisfied(self, *, action: str, entity_id: UUID, actor_user_id: UUID) -> bool: ...


AuditWriter = Callable[[Session, AuditEventInput], object]

_ASSET_TRANSITIONS: dict[str, frozenset[str]] = {
    "available": frozenset({"repair", "damaged", "disposed"}),
    "allocated": frozenset({"repair", "damaged"}),
    "repair": frozenset({"available", "damaged", "disposed"}),
    "damaged": frozenset({"repair", "disposed"}),
    "disposed": frozenset(),
}


def validate_asset_transition(current: str, target: str) -> None:
    """Reject invalid lifecycle edges; allocation has its own custody workflow."""
    if target not in _ASSET_TRANSITIONS.get(current, frozenset()):
        raise AppError("INVALID_WORKFLOW_TRANSITION", "The asset lifecycle transition is not valid.", 409)


def _require_policy(policy: WorkflowPolicy | None, *, actor: UUID, capability: str,
                    entity_type: str, entity_id: UUID, approval_action: str | None = None) -> None:
    if policy is None:
        raise AppError("WORKFLOW_UNAVAILABLE", "Required workflow authorization is unavailable.", 503)
    try:
        if policy.authorize(actor_user_id=actor, capability=capability,
                           entity_type=entity_type, entity_id=entity_id) is not True:
            raise AppError("FORBIDDEN", "This operation is not permitted.", 403)
        if approval_action and policy.approval_satisfied(
            action=approval_action, entity_id=entity_id, actor_user_id=actor
        ) is not True:
            raise AppError("APPROVAL_REQUIRED", "Required independent approval is unavailable.", 403)
    except AppError:
        raise
    except Exception:
        raise AppError("WORKFLOW_UNAVAILABLE", "Required workflow authorization is unavailable.", 503) from None


def transition_asset(
    session: Session, *, asset_id: UUID, actor_user_id: UUID, target: str,
    policy: WorkflowPolicy | None, audit_writer: AuditWriter = write_audit_event,
) -> str:
    """Lock, authorize, audit, and update atomically inside a caller-owned transaction."""
    _require_policy(policy, actor=actor_user_id, capability="assets:update",
                    entity_type="tracked_asset", entity_id=asset_id,
                    approval_action="asset_disposal" if target == "disposed" else None)
    try:
        with session.begin_nested():
            asset = session.execute(select(TrackedAsset).where(TrackedAsset.id == asset_id)
                                    .with_for_update()).scalar_one_or_none()
            if asset is None:
                raise AppError("NOT_FOUND", "Asset was not found.", 404)
            previous = asset.lifecycle_status
            validate_asset_transition(previous, target)
            audit_writer(session, AuditEventInput(
                actor_user_id=actor_user_id, action="asset.lifecycle_updated",
                entity_type="tracked_asset", entity_id=asset_id,
                metadata={"changed_fields": ["lifecycle_status"]},
                previous_values={"lifecycle_status": previous},
                updated_values={"lifecycle_status": target},
            ))
            asset.lifecycle_status = target
            session.flush()
            return target
    except AppError:
        raise
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The inventory update could not be completed.", 503) from None


def complete_exit_clearance(
    session: Session, *, clearance_id: UUID, actor_user_id: UUID,
    policy: WorkflowPolicy | None, audit_writer: AuditWriter = write_audit_event,
) -> None:
    """Complete only verified clearance with no active individual or quantity lines."""
    _require_policy(policy, actor=actor_user_id, capability="exit_clearance:complete",
                    entity_type="employee_exit_clearance", entity_id=clearance_id,
                    approval_action="exit_clearance_completion")
    try:
        with session.begin_nested():
            clearance = session.execute(select(EmployeeExitClearance).where(
                EmployeeExitClearance.id == clearance_id).with_for_update()).scalar_one_or_none()
            if clearance is None:
                raise AppError("NOT_FOUND", "Exit clearance was not found.", 404)
            if clearance.status not in {"pending", "in_progress"} or clearance.verification_status != "verified":
                raise AppError("EXIT_CLEARANCE_INCOMPLETE", "Required exit verification is incomplete.", 409)
            approval = session.execute(select(WorkflowApproval).where(
                WorkflowApproval.entity_type == "exit_clearance",
                WorkflowApproval.entity_id == clearance_id,
                WorkflowApproval.status == "approved").with_for_update()).scalar_one_or_none()
            if approval is None or (approval.decided_by_id == clearance.opened_by_id
                                    and not _self_approval_allowed(policy, "exit_clearance")):
                raise AppError("APPROVAL_REQUIRED", "An independent clearance approval is required.", 403)
            outstanding = session.execute(select(AllocationLine.id).join(
                Allocation, AllocationLine.allocation_id == Allocation.id
            ).where(
                Allocation.employee_id == clearance.employee_id,
                AllocationLine.status.in_(("pending", "active", "partially_returned")),
            ).with_for_update()).first()
            if outstanding is not None:
                raise AppError("EXIT_CLEARANCE_INCOMPLETE", "Assigned inventory remains outstanding.", 409)
            audit_writer(session, AuditEventInput(
                actor_user_id=actor_user_id, action="exit_clearance.completed",
                entity_type="employee_exit_clearance", entity_id=clearance_id,
                metadata={"changed_fields": ["clearance_status"]},
                previous_values={"clearance_status": clearance.status},
                updated_values={"clearance_status": "completed"},
            ))
            clearance.status = "completed"
            clearance.completed_by_id = actor_user_id
            clearance.completed_at = datetime.now(timezone.utc)
            session.flush()
    except AppError:
        raise
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "Exit clearance could not be completed.", 503) from None
