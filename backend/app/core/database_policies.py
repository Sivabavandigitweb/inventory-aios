"""Request-scoped DB-backed policy composition with deny-by-default scope checks."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authentication import Principal, RolePermissionPolicy, principal_for_local_user
from app.core.operational_policies import WorkflowApprovalConfiguration
from app.core.permission_catalog import is_known_capability
from app.models import WorkflowApproval


class ResourceScopePolicy(Protocol):
    def can_access(
        self, *, user_id: UUID, capability: str, entity_type: str, entity_id: UUID | None
    ) -> bool: ...


_ADMIN_INVENTORY_ENTITY_TYPES = frozenset(
    {
        "allocation", "allocation_history", "allocation_line", "asset_registration",
        "asset_registration_request", "asset_repair", "disposal_request", "employee",
        "employee_exit_clearance", "inventory_balance", "inventory_product",
        "inventory_return", "location", "product", "quantity_disposition",
        "quantity_disposition_request", "quantity_inventory_lot", "quantity_registration",
        "quantity_registration_request", "receipt", "receipt_line", "receiving",
        "registration_candidates", "registration_finalizations", "return", "return_history",
        "tracked_asset", "workflow_approval",
    }
)


class OrganizationWideInventoryAdminScopePolicy:
    """Recheck active inventory-admin role for the approved global admin scope.

    Management approved both individually assigned administrators for inventory
    administration. This scope does not grant summary access and rejects unknown
    capability/entity labels; normal capability policy remains independently
    required by ``DatabaseInventoryWritePolicy``.
    """

    def __init__(self, *, session: Session, role_policy: RolePermissionPolicy) -> None:
        self._session = session
        self._role_policy = role_policy

    def can_access(
        self, *, user_id: UUID, capability: str, entity_type: str, entity_id: UUID | None
    ) -> bool:
        if (
            not isinstance(user_id, UUID)
            or not is_known_capability(capability)
            or entity_type not in _ADMIN_INVENTORY_ENTITY_TYPES
            or entity_id is not None and not isinstance(entity_id, UUID)
        ):
            return False
        try:
            current = principal_for_local_user(user_id, self._session, self._role_policy)
            return (
                "inventory_administrator" in current.roles
                and capability in current.permissions
            )
        except Exception:
            return False


_APPROVAL_CAPABILITY = {
    "product_catalog": "approvals:decide:product_catalog",
    "receiving": "approvals:decide:receiving",
    "asset_registration": "approvals:decide:asset_registration",
    "quantity_registration": "approvals:decide:quantity_registration",
    "allocation": "approvals:decide:allocation",
    "allocation_issue": "approvals:decide:allocation",
    "return": "approvals:decide:return",
    "return_verification": "approvals:decide:return",
    "repair": "approvals:decide:repair",
    "asset_disposal": "approvals:decide:disposal",
    "quantity_disposition": "approvals:decide:quantity_disposition",
    "exit_clearance": "approvals:decide:exit_clearance",
}


class DatabaseInventoryWritePolicy:
    """Enforce current role/capability and injected resource scope on every call.

    This class is not wired as an operational default. A caller must explicitly
    inject its role mapping, scope policy, approval configuration, and request DB
    session. Missing scope or approval evidence denies access.
    """

    def __init__(
        self,
        *,
        session: Session,
        actor: Principal,
        role_policy: RolePermissionPolicy,
        resource_scope: ResourceScopePolicy,
        approval_configuration: WorkflowApprovalConfiguration,
        repair_currency_codes: frozenset[str] | None = None,
    ) -> None:
        self._session = session
        self._actor = actor
        self._role_policy = role_policy
        self._resource_scope = resource_scope
        self._approval_configuration = approval_configuration
        self._repair_currency_codes = repair_currency_codes or frozenset()

    def authorize(
        self, *, actor_user_id: UUID, capability: str, entity_type: str, entity_id: UUID | None
    ) -> bool:
        try:
            if actor_user_id != self._actor.user_id or not is_known_capability(capability):
                return False
            current = principal_for_local_user(actor_user_id, self._session, self._role_policy)
            if capability not in current.permissions:
                return False
            return self._resource_scope.can_access(
                user_id=actor_user_id,
                capability=capability,
                entity_type=entity_type,
                entity_id=entity_id,
            ) is True
        except Exception:
            return False

    def requires_approval(self, *, action: str) -> bool:
        # Unknown writes require approval as well; no action name silently opts out.
        return True

    def allows_self_approval(self, action: str) -> bool:
        return self._approval_configuration.allows_self_approval(action)

    def allows_repair_cost_currency(self, code: str) -> bool:
        return isinstance(code, str) and code in self._repair_currency_codes

    def approval_satisfied(
        self, *, action: str, entity_id: UUID, actor_user_id: UUID
    ) -> bool:
        capability = _APPROVAL_CAPABILITY.get(action)
        if capability is None or not is_known_capability(capability):
            return False
        try:
            approval = self._session.execute(
                select(WorkflowApproval).where(
                    WorkflowApproval.entity_id == entity_id,
                    WorkflowApproval.required_capability == capability,
                    WorkflowApproval.status == "approved",
                ).with_for_update(read=True)
            ).scalar_one_or_none()
            if (approval is None or not isinstance(approval.decided_by_id, UUID)
                    or not isinstance(approval.decided_at, datetime)):
                return False
            requester_id = approval.requested_by_id
            if requester_id == approval.decided_by_id and not self.allows_self_approval(action):
                return False
            approver = principal_for_local_user(
                approval.decided_by_id, self._session, self._role_policy
            )
            return capability in approver.permissions and actor_user_id == self._actor.user_id
        except Exception:
            return False
