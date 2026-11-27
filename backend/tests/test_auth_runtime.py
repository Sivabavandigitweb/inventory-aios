import pytest

from app.core.auth_runtime import (
    AuthenticationActivationEvidence,
    AuthenticationNotReady,
    AuthenticationRuntimeConfiguration,
    assert_authentication_activation_ready,
)


def test_runtime_authentication_is_disabled_by_default() -> None:
    config = AuthenticationRuntimeConfiguration()
    assert config.enabled is False
    with pytest.raises(AuthenticationNotReady):
        assert_authentication_activation_ready(config, AuthenticationActivationEvidence())


def test_enabled_configuration_requires_explicit_secure_values() -> None:
    with pytest.raises(ValueError):
        AuthenticationRuntimeConfiguration(enabled=True)
    base = {
        "enabled": True,
        "cookie_name": "__Host-inventory-session",
        "same_site": "strict",
        "trusted_origins": ("https://inventory.example.invalid",),
        "csrf_signing_key": "fictional-test-key-material-long-enough-000000",
        "csrf_token_lifetime_seconds": 300,
        "cookie_max_age_seconds": 1800,
        "absolute_session_lifetime_seconds": 28800,
        "inactivity_timeout_seconds": 1800,
    }
    config = AuthenticationRuntimeConfiguration(**base)
    assert config.enabled is True
    with pytest.raises(ValueError):
        AuthenticationRuntimeConfiguration(**{**base, "trusted_origins": ("http://example.invalid",)})
    with pytest.raises(ValueError):
        AuthenticationRuntimeConfiguration(**{**base, "cookie_name": "inventory-session"})


def test_activation_gate_lists_unapproved_policy_and_operational_gates() -> None:
    config = AuthenticationRuntimeConfiguration(
        enabled=True,
        cookie_name="__Host-inventory-session",
        same_site="strict",
        trusted_origins=("https://inventory.example.invalid",),
        csrf_signing_key="fictional-test-key-material-long-enough-000000",
        csrf_token_lifetime_seconds=300,
        cookie_max_age_seconds=1800,
        absolute_session_lifetime_seconds=28800,
        inactivity_timeout_seconds=1800,
    )
    with pytest.raises(AuthenticationNotReady) as error:
        assert_authentication_activation_ready(config, AuthenticationActivationEvidence())
    assert "AUTH-07" in error.value.blockers
    assert "authentication migration and schema verification" in error.value.blockers
    assert "production CSRF deployment" in error.value.blockers


def test_full_evidence_only_passes_validation_gate_and_does_not_register_routes() -> None:
    config = AuthenticationRuntimeConfiguration(
        enabled=True,
        cookie_name="__Host-inventory-session",
        same_site="strict",
        trusted_origins=("https://inventory.example.invalid",),
        csrf_signing_key="fictional-test-key-material-long-enough-000000",
        csrf_token_lifetime_seconds=300,
        cookie_max_age_seconds=1800,
        absolute_session_lifetime_seconds=28800,
        inactivity_timeout_seconds=1800,
    )
    evidence = AuthenticationActivationEvidence(
        approved_decisions=frozenset({"AUTH-01", "AUTH-02", "AUTH-03", "AUTH-04", "AUTH-05", "AUTH-06", "AUTH-07", "AUTH-13"}),
        migration_verified=True,
        runtime_privileges_verified=True,
        individual_accounts_provisioned=True,
        production_csrf_verified=True,
        mfa_decision_recorded=True,
        distributed_attempt_protection_verified=True,
        audit_writer_verified=True,
        real_browser_security_verified=True,
    )
    assert_authentication_activation_ready(config, evidence)
