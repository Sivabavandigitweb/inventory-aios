"""Closed, explicit role-to-capability mappings for approved account roles.

Role names never bypass policy. Provisioning must assign these role codes and
authorization still checks the user's current, time-valid assignments.
"""

from __future__ import annotations

from types import MappingProxyType

from app.core.authentication import RolePermissionPolicy
from app.core.permission_catalog import CAPABILITY_IDS, Capability

_INVENTORY_ADMIN = frozenset(
    {
        Capability.DASHBOARD_OPERATIONAL_READ.value,
        Capability.ASSETS_READ.value,
        Capability.ASSETS_CREATE.value,
        Capability.ASSETS_UPDATE.value,
        Capability.PRODUCTS_READ.value,
        Capability.PRODUCTS_MANAGE.value,
        Capability.RECEIPTS_READ.value,
        Capability.RECEIPTS_CREATE.value,
        Capability.RECEIPTS_REGISTER_ASSET.value,
        Capability.QUANTITY_INVENTORY_READ.value,
        Capability.QUANTITY_REGISTER.value,
        Capability.QUANTITY_INVENTORY_ADJUST.value,
        Capability.EMPLOYEES_READ_ALL.value,
        Capability.EMPLOYEE_SYNC_RUN.value,
        Capability.EMPLOYEE_SYNC_REVIEW.value,
        Capability.ALLOCATIONS_READ.value,
        Capability.ALLOCATIONS_CREATE.value,
        Capability.ALLOCATIONS_UPDATE.value,
        Capability.ALLOCATIONS_CANCEL.value,
        Capability.RETURNS_READ.value,
        Capability.RETURNS_RECORD.value,
        Capability.RETURNS_VERIFY.value,
        Capability.REPAIRS_READ.value,
        Capability.REPAIRS_REPORT.value,
        Capability.REPAIRS_UPDATE.value,
        Capability.APPROVALS_REPAIR.value,
        Capability.APPROVALS_EXIT_CLEARANCE.value,
        Capability.APPROVALS_QUANTITY_DISPOSITION.value,
        Capability.QUANTITY_DISPOSITION_REQUEST.value,
        Capability.QUANTITY_DISPOSITION_DECIDE.value,
        Capability.DISPOSALS_READ.value,
        Capability.EXIT_CLEARANCE_OPEN.value,
        Capability.EXIT_CLEARANCE_CANCEL.value,
        Capability.EXIT_CLEARANCE_READ.value,
        Capability.EXIT_CLEARANCE_COMPLETE.value,
        Capability.APPROVALS_READ.value,
        Capability.APPROVALS_ASSET_REGISTRATION.value,
        Capability.APPROVALS_PRODUCT_CATALOG.value,
        Capability.APPROVALS_RECEIVING.value,
        Capability.APPROVALS_QUANTITY_REGISTRATION.value,
        Capability.APPROVALS_ALLOCATION.value,
        Capability.APPROVALS_RETURN.value,
        Capability.APPROVALS_DISPOSAL.value,
        Capability.DISPOSALS_REQUEST.value,
        Capability.DISPOSALS_FINALIZE.value,
        Capability.NOTIFICATIONS_READ.value,
        Capability.NOTIFICATIONS_MANAGE.value,
        Capability.REPORTS_READ.value,
        Capability.REPORTS_EXPORT.value,
        Capability.AI_INVOKE.value,
    }
)

_SECURITY_ADMIN = frozenset(
    {
        Capability.USERS_PROVISION.value,
        Capability.USERS_DEACTIVATE.value,
        Capability.CREDENTIALS_RECOVER.value,
        Capability.ROLES_ASSIGN.value,
        Capability.PERMISSIONS_ADMIN.value,
        Capability.SECURITY_CONFIGURE.value,
        Capability.AUDIT_READ.value,
    }
)

APPROVED_ROLE_CAPABILITIES = MappingProxyType(
    {
        "inventory_administrator": _INVENTORY_ADMIN,
        "security_administrator": _SECURITY_ADMIN,
    }
)


class ExplicitRolePermissionPolicy(RolePermissionPolicy):
    """Resolve only explicitly enumerated, known role and capability values."""

    def __init__(self, role_capabilities=None) -> None:
        source = APPROVED_ROLE_CAPABILITIES if role_capabilities is None else role_capabilities
        normalized: dict[str, frozenset[str]] = {}
        for role, capabilities in source.items():
            if not isinstance(role, str) or not role or role != role.strip():
                raise ValueError("Role codes must be non-empty exact strings.")
            values = frozenset(capabilities)
            if any(not isinstance(value, str) or value not in CAPABILITY_IDS for value in values):
                raise ValueError("Role mapping contains an unknown capability.")
            normalized[role] = values
        self._mapping = MappingProxyType(normalized)

    def permissions_for(self, role_codes: set[str]) -> frozenset[str]:
        if not isinstance(role_codes, set) or any(role not in self._mapping for role in role_codes):
            return frozenset()
        return frozenset().union(*(self._mapping[role] for role in role_codes))


ADMINISTRATOR_ROLE_ASSIGNMENTS = MappingProxyType(
    {
        "super_admin": ("inventory_administrator", "security_administrator"),
        "system_admin": ("inventory_administrator",),
    }
)
