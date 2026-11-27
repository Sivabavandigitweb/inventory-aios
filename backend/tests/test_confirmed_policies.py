from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.core.auth_runtime import (
    AuthenticationRuntimeConfiguration,
    session_policy_from_configuration,
)
from app.core.credential_verification import canonicalize_ascii_username
from app.core.errors import AppError
from app.db.auth_repositories import postgres_lower_ascii_username_predicate
from app.services.workflow_operations import (
    APPROVED_DISPOSAL_REASONS,
    request_disposal,
)


def test_confirmed_ascii_username_normalization_matches_ascii_lowercase_contract() -> None:
    assert canonicalize_ascii_username("Super_Admin") == "super_admin"
    assert canonicalize_ascii_username("system_admin") == "system_admin"


@pytest.mark.parametrize("username", ["", " super_admin", "system_admin ", "ümlaut"])
def test_ascii_username_normalization_rejects_noncanonical_input(username: str) -> None:
    with pytest.raises(ValueError):
        canonicalize_ascii_username(username)


def test_postgres_username_predicate_matches_existing_lower_expression_index() -> None:
    predicate = postgres_lower_ascii_username_predicate("super_admin")
    compiled = predicate.compile(dialect=postgresql.dialect())
    assert "lower(users.username)" in str(compiled)
    assert list(compiled.params.values()) == ["super_admin"]
    with pytest.raises(ValueError):
        postgres_lower_ascii_username_predicate("Super_Admin")


def test_confirmed_session_maximums_reject_excessive_configured_durations() -> None:
    config = {
        "enabled": True,
        "cookie_name": "__Host-inventory-session",
        "same_site": "strict",
        "trusted_origins": ("https://inventory.example.invalid",),
        "csrf_signing_key": "fictional-test-key-material-long-enough-000000",
        "csrf_token_lifetime_seconds": 300,
        "cookie_max_age_seconds": 32_401,
        "absolute_session_lifetime_seconds": 32_401,
        "inactivity_timeout_seconds": 1_801,
    }
    with pytest.raises(ValueError):
        AuthenticationRuntimeConfiguration(**config)


def test_session_policy_uses_confirmed_lifetimes_and_requires_activity_interval() -> None:
    config = AuthenticationRuntimeConfiguration(
        absolute_session_lifetime_seconds=28_800,
        inactivity_timeout_seconds=1_800,
    )
    policy = session_policy_from_configuration(config, activity_update_interval_seconds=0)
    assert policy.absolute_lifetime.total_seconds() == 28_800
    assert policy.inactivity_timeout.total_seconds() == 1_800
    assert policy.activity_update_interval.total_seconds() == 0


def test_disposal_reason_is_limited_to_confirmed_management_values() -> None:
    assert set(APPROVED_DISPOSAL_REASONS) == {
        "damaged_beyond_repair", "obsolete", "end_of_useful_life", "uneconomical_repair",
    }
    session = MagicMock()
    with pytest.raises(AppError) as error:
        request_disposal(
            session,
            asset_id=uuid4(),
            actor_user_id=uuid4(),
            reason_code="test-or-invented-reason",
            condition=None,
            idempotency_key="fictional-disposal-test",
            policy=MagicMock(),
        )
    assert error.value.status_code == 422
    session.execute.assert_not_called()
