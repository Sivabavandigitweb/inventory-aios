"""Explicitly configured business policies; importing this module activates none."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from app.core.credential_verification import VerifiedCredential
from app.core.login_orchestration import AuthenticationCompletionDecision

APPROVED_REPAIR_CURRENCY_CODES = frozenset({"LKR", "GBP", "USD", "EUR"})


MANAGEMENT_APPROVED_SINGLE_APPROVER_ACTIONS = frozenset({
    "asset_registration",
    "allocation",
    "return",
    "repair",
    "asset_disposal",
    "quantity_disposition",
    "exit_clearance",
})


@dataclass(frozen=True, slots=True)
class WorkflowApprovalConfiguration:
    """Management-approved single explicit approval for the named workflows."""

    self_approval_actions: frozenset[str] = MANAGEMENT_APPROVED_SINGLE_APPROVER_ACTIONS

    def __post_init__(self) -> None:
        if not self.self_approval_actions <= MANAGEMENT_APPROVED_SINGLE_APPROVER_ACTIONS:
            raise ValueError("Self-approval configuration contains an unapproved workflow.")

    def allows_self_approval(self, action: str) -> bool:
        return isinstance(action, str) and action in self.self_approval_actions


@dataclass(frozen=True, slots=True)
class ApprovedRepairCurrencyPolicy:
    """Management-confirmed currency codes, with no implied conversion rule."""

    codes: frozenset[str] = APPROVED_REPAIR_CURRENCY_CODES

    def __post_init__(self) -> None:
        if not self.codes or any(
            not isinstance(code, str)
            or len(code) != 3
            or not code.isascii()
            or not code.isalpha()
            or code != code.upper()
            for code in self.codes
        ):
            raise ValueError("Repair currencies must be explicit uppercase three-letter codes.")

    def allows(self, code: str) -> bool:
        return isinstance(code, str) and code in self.codes


class ApprovedPasswordOnlyCompletionPolicy:
    """Explicit implementation of management's password-only decision.

    Construction is required; no composition path selects it implicitly.
    """

    def evaluate(self, verified: VerifiedCredential) -> AuthenticationCompletionDecision:
        if not isinstance(verified, VerifiedCredential):
            return AuthenticationCompletionDecision.DENY
        return AuthenticationCompletionDecision.COMPLETE


REVISED_APPROVAL_ACTIONS = MappingProxyType(
    {
        "asset_registration": "asset_registration",
        "quantity_registration": "quantity_registration",
        "allocation": "allocation",
        "return": "return",
        "repair": "repair",
        "asset_disposal": "asset_disposal",
        "quantity_disposition": "quantity_disposition",
        "exit_clearance": "exit_clearance",
    }
)
