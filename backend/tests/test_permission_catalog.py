from uuid import uuid4

import pytest

from app.core.authentication import Principal, _valid_permissions
from app.core.authorization import authorize_resource, require_permission
from app.core.errors import AppError
from app.core.permission_catalog import CAPABILITY_IDS, Capability


def test_candidate_catalog_is_explicit_and_contains_no_wildcards() -> None:
    assert Capability.EMPLOYEES_READ_ALL.value in CAPABILITY_IDS
    assert Capability.APPROVALS_ALLOCATION.value in CAPABILITY_IDS
    assert Capability.SUMMARY_APPROVED_READ.value in CAPABILITY_IDS
    assert all("*" not in item for item in CAPABILITY_IDS)


def test_unknown_or_malformed_policy_capabilities_fail_closed() -> None:
    assert not _valid_permissions(frozenset({"unknown:grant"}))
    assert not _valid_permissions(frozenset({"employees:*"}))
    assert _valid_permissions(frozenset({"employees:read:all"}))
    with pytest.raises(ValueError, match="Unknown capability"):
        require_permission("unknown:grant")


def test_admin_role_name_does_not_bypass_explicit_capability_check() -> None:
    principal = Principal(uuid4(), frozenset(), roles=frozenset({"inventory_admin"}))
    dependency = require_permission(Capability.ASSETS_UPDATE.value)
    with pytest.raises(AppError) as error:
        dependency(principal)
    assert error.value.status_code == 403


def test_resource_scope_is_checked_after_capability() -> None:
    user_id = uuid4()
    resource_id = uuid4()

    class AllowScope:
        def can_access(self, **kwargs):
            assert kwargs["user_id"] == user_id
            assert kwargs["resource_id"] == resource_id
            return True

    principal = Principal(user_id, frozenset({Capability.ALLOCATIONS_READ.value}))
    authorize_resource(
        principal,
        capability=Capability.ALLOCATIONS_READ.value,
        resource_type="allocation",
        resource_id=resource_id,
        authorizer=AllowScope(),
    )

    class InvalidScope:
        def can_access(self, **kwargs):
            return "yes"

    with pytest.raises(AppError) as error:
        authorize_resource(
            principal,
            capability=Capability.ALLOCATIONS_READ.value,
            resource_type="allocation",
            resource_id=resource_id,
            authorizer=InvalidScope(),
        )
    assert error.value.status_code == 403


def test_candidate_role_mapping_is_local_to_test_and_not_production_policy() -> None:
    # This fake is intentionally not registered as the runtime policy.
    candidate_test_mapping = {"inventory_admin": frozenset({Capability.ASSETS_READ.value})}
    assert candidate_test_mapping["inventory_admin"] == frozenset({"assets:read"})
    from app.core.authentication import get_role_permission_policy

    assert get_role_permission_policy().permissions_for({"inventory_admin"}) == frozenset()
