"""Fail-closed authentication activation configuration and release gate.

This module does not read environment files or register routes. Callers must pass
explicit configuration and evidence from approved release/database/browser gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, SecretStr, model_validator

from app.core.sessions import SessionPolicy

APPROVED_MAX_ABSOLUTE_SESSION_SECONDS = 8 * 60 * 60
APPROVED_MAX_IDLE_SESSION_SECONDS = 30 * 60


class AuthenticationNotReady(RuntimeError):
    def __init__(self, blockers: tuple[str, ...]) -> None:
        self.blockers = blockers
        super().__init__("Operational authentication prerequisites are incomplete.")


class AuthenticationRuntimeConfiguration(BaseModel):
    """Explicit, non-environment-loaded configuration; disabled unless requested."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    cookie_name: str | None = None
    same_site: Literal["strict", "lax"] | None = None
    trusted_origins: tuple[str, ...] = ()
    csrf_signing_key: SecretStr | None = None
    csrf_token_lifetime_seconds: int | None = None
    cookie_max_age_seconds: int | None = None
    absolute_session_lifetime_seconds: int | None = None
    inactivity_timeout_seconds: int | None = None

    @model_validator(mode="after")
    def validate_enabled_configuration(self):
        if not self.enabled:
            return self
        if (
            self.cookie_name is None
            or self.same_site is None
            or not self.trusted_origins
            or self.csrf_signing_key is None
            or self.csrf_token_lifetime_seconds is None
            or self.cookie_max_age_seconds is None
            or self.absolute_session_lifetime_seconds is None
            or self.inactivity_timeout_seconds is None
        ):
            raise ValueError("Enabled authentication requires explicit security configuration.")
        if any(not origin.startswith("https://") for origin in self.trusted_origins):
            raise ValueError("Enabled authentication requires exact HTTPS origins.")
        if not self.cookie_name.startswith("__Host-") or self.same_site not in ("strict", "lax"):
            raise ValueError("Authentication cookie must be secure, host-only, and explicitly scoped.")
        if self.cookie_name == "__Host-":
            raise ValueError("Authentication cookie name is invalid.")
        for origin in self.trusted_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "https"
                or not parsed.netloc
                or parsed.hostname is None
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
                or parsed.port is not None and not 1 <= parsed.port <= 65535
            ):
                raise ValueError("Trusted origins must be exact HTTPS origins.")
        if len(self.csrf_signing_key.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("CSRF signing key is too short.")
        if any(
            type(value) is not int or value <= 0
            for value in (
                self.csrf_token_lifetime_seconds,
                self.cookie_max_age_seconds,
                self.absolute_session_lifetime_seconds,
                self.inactivity_timeout_seconds,
            )
        ):
            raise ValueError("Authentication lifetimes must be positive integers.")
        if (
            self.csrf_token_lifetime_seconds > self.cookie_max_age_seconds
            or self.cookie_max_age_seconds > self.absolute_session_lifetime_seconds
            or self.inactivity_timeout_seconds > self.absolute_session_lifetime_seconds
        ):
            raise ValueError("Authentication cookie and session lifetimes are inconsistent.")
        if (
            self.absolute_session_lifetime_seconds > APPROVED_MAX_ABSOLUTE_SESSION_SECONDS
            or self.inactivity_timeout_seconds > APPROVED_MAX_IDLE_SESSION_SECONDS
        ):
            raise ValueError("Authentication session lifetimes exceed the approved maximums.")
        return self


def session_policy_from_configuration(
    configuration: AuthenticationRuntimeConfiguration,
    *,
    activity_update_interval_seconds: int,
) -> SessionPolicy:
    """Build a session policy under management-confirmed absolute/idle ceilings.

    The activity write interval remains an explicit caller-supplied operational
    setting because management has not selected one.
    """
    absolute = configuration.absolute_session_lifetime_seconds
    idle = configuration.inactivity_timeout_seconds
    if absolute is None or idle is None:
        raise ValueError("Explicit absolute and idle session durations are required.")
    if type(activity_update_interval_seconds) is not int or activity_update_interval_seconds < 0:
        raise ValueError("The activity update interval must be a non-negative integer.")
    return SessionPolicy(
        absolute_lifetime=timedelta(seconds=absolute),
        inactivity_timeout=timedelta(seconds=idle),
        activity_update_interval=timedelta(seconds=activity_update_interval_seconds),
        maximum_absolute_lifetime=timedelta(seconds=APPROVED_MAX_ABSOLUTE_SESSION_SECONDS),
    )


@dataclass(frozen=True, slots=True)
class AuthenticationActivationEvidence:
    approved_decisions: frozenset[str] = frozenset()
    migration_verified: bool = False
    runtime_privileges_verified: bool = False
    individual_accounts_provisioned: bool = False
    production_csrf_verified: bool = False
    mfa_decision_recorded: bool = False
    distributed_attempt_protection_verified: bool = False
    audit_writer_verified: bool = False
    real_browser_security_verified: bool = False


@dataclass(frozen=True, slots=True)
class InventoryWriteActivationEvidence:
    """Independent release evidence for operational inventory mutation routes."""

    approved_workflow_policies: bool = False
    migration_verified: bool = False
    runtime_privileges_verified: bool = False
    audit_writer_verified: bool = False
    transaction_integration_tests_verified: bool = False


class InventoryWritesNotReady(RuntimeError):
    def __init__(self, blockers: tuple[str, ...]) -> None:
        self.blockers = blockers
        super().__init__("Operational inventory writes are not ready.")


def assert_inventory_writes_ready(evidence: InventoryWriteActivationEvidence) -> None:
    blockers = tuple(
        label for label, ready in (
            ("approved workflow and approval policies", evidence.approved_workflow_policies),
            ("inventory migration verification", evidence.migration_verified),
            ("least-privilege inventory runtime privileges", evidence.runtime_privileges_verified),
            ("transactional audit writer verification", evidence.audit_writer_verified),
            ("PostgreSQL transaction and concurrency tests", evidence.transaction_integration_tests_verified),
        ) if ready is not True
    )
    if blockers:
        raise InventoryWritesNotReady(blockers)


_REQUIRED_DECISIONS = frozenset(
    {"AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04", "AUTH-05", "AUTH-06", "AUTH-07", "AUTH-13"}
)


def assert_authentication_activation_ready(
    configuration: AuthenticationRuntimeConfiguration,
    evidence: AuthenticationActivationEvidence,
) -> None:
    if not configuration.enabled:
        raise AuthenticationNotReady(("authentication is explicitly disabled",))
    blockers: list[str] = []
    blockers.extend(sorted(_REQUIRED_DECISIONS - evidence.approved_decisions))
    for label, ready in (
        ("authentication migration and schema verification", evidence.migration_verified),
        ("least-privilege runtime privileges", evidence.runtime_privileges_verified),
        ("individual account provisioning", evidence.individual_accounts_provisioned),
        ("production CSRF deployment", evidence.production_csrf_verified),
        ("MFA decision", evidence.mfa_decision_recorded),
        ("distributed login-attempt protection", evidence.distributed_attempt_protection_verified),
        ("audit writer and actor attribution", evidence.audit_writer_verified),
        ("real-browser security verification", evidence.real_browser_security_verified),
    ):
        if not ready:
            blockers.append(label)
    if blockers:
        raise AuthenticationNotReady(tuple(blockers))
