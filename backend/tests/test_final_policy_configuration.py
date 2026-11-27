from datetime import timedelta
from uuid import uuid4

import pytest

from app.core.login_orchestration import LoginAttemptContext
from app.core.operational_policies import (
    APPROVED_REPAIR_CURRENCY_CODES,
    ApprovedPasswordOnlyCompletionPolicy,
    ApprovedRepairCurrencyPolicy,
    WorkflowApprovalConfiguration,
)
from app.core.permission_catalog import Capability
from app.core.permission_policy import (
    ADMINISTRATOR_ROLE_ASSIGNMENTS,
    ExplicitRolePermissionPolicy,
)
from app.core.postgres_login_protection import (
    LoginProtectionPolicy,
    PostgresLoginAttemptProtection,
)


def test_administrator_capabilities_are_explicit_and_username_does_not_bypass() -> None:
    policy = ExplicitRolePermissionPolicy()
    inventory = policy.permissions_for({"inventory_administrator"})
    security = policy.permissions_for({"security_administrator"})
    assert Capability.ALLOCATIONS_CREATE.value in inventory
    assert Capability.APPROVALS_ALLOCATION.value in inventory
    assert Capability.USERS_PROVISION.value not in inventory
    assert Capability.AUDIT_READ.value not in inventory
    assert Capability.USERS_PROVISION.value in security
    assert Capability.AUDIT_READ.value in security
    assert Capability.AUDIT_EXPORT.value not in security
    assert policy.permissions_for({"inventory_administrator", "unrecognized"}) == frozenset()
    assert ADMINISTRATOR_ROLE_ASSIGNMENTS == {
        "super_admin": ("inventory_administrator", "security_administrator"),
        "system_admin": ("inventory_administrator",),
    }


def test_management_single_approval_policy_is_explicit_for_approved_workflows() -> None:
    default = WorkflowApprovalConfiguration()
    assert default.allows_self_approval("asset_registration")
    assert default.allows_self_approval("allocation")
    assert default.allows_self_approval("return")
    assert default.allows_self_approval("repair")
    assert default.allows_self_approval("asset_disposal")
    assert default.allows_self_approval("quantity_disposition")
    assert default.allows_self_approval("exit_clearance")
    assert not default.allows_self_approval("quantity_registration")
    assert not default.allows_self_approval("receiving")
    with pytest.raises(ValueError):
        WorkflowApprovalConfiguration(self_approval_actions=frozenset({"user_provision"}))


def test_confirmed_password_only_and_repair_currency_policy_are_explicit() -> None:
    from app.core.credential_verification import VerifiedCredential
    verified = VerifiedCredential(user_id=uuid4(), credential_version=1, rehash_recommended=False)
    from app.core.login_orchestration import AuthenticationCompletionDecision
    assert ApprovedPasswordOnlyCompletionPolicy().evaluate(verified) is AuthenticationCompletionDecision.COMPLETE
    currencies = ApprovedRepairCurrencyPolicy()
    assert currencies.codes == APPROVED_REPAIR_CURRENCY_CODES == {"LKR", "GBP", "USD", "EUR"}
    assert all(currencies.allows(code) for code in currencies.codes)
    assert not currencies.allows("JPY")
    with pytest.raises(ValueError):
        ApprovedRepairCurrencyPolicy(frozenset({"usd"}))


def test_distributed_login_policy_matches_approved_attempt_limits() -> None:
    policy = LoginProtectionPolicy()
    assert policy.maximum_failures == 5
    assert policy.window == timedelta(minutes=15)
    assert policy.restriction == timedelta(minutes=15)
    with pytest.raises(ValueError):
        LoginProtectionPolicy(maximum_failures=0)


def test_login_attempt_keys_are_hmac_digests_and_require_trusted_ip() -> None:
    service = PostgresLoginAttemptProtection(
        session_factory=object(), hmac_key=b"x" * 32, policy=LoginProtectionPolicy()
    )
    account, source = service._digests(LoginAttemptContext("Super_Admin", "192.0.2.10"))
    assert len(account[1]) == 32 and len(source[1]) == 32
    assert b"super_admin" not in account[1]
    assert b"192.0.2.10" not in source[1]
    with pytest.raises(ValueError):
        service._digests(LoginAttemptContext("system_admin", "spoofed-forwarded-for"))
