from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.auth_runtime import (
    AuthenticationActivationEvidence,
    AuthenticationNotReady,
    AuthenticationRuntimeConfiguration,
    InventoryWriteActivationEvidence,
    InventoryWritesNotReady,
    assert_inventory_writes_ready,
)
from app.core.errors import AppError
from app.core.permission_catalog import Capability, is_known_capability
from app.schemas.inventory import (
    ProductCreate,
    ReceiptCreate,
    ReceiptLineCreate,
    WorkflowApprovalDecision,
)
from app.services.inventory_writes import (
    _approval_required,
    _authorize,
    create_product,
    create_receipt,
    list_registration_candidates,
    list_registration_finalizations,
)


class AllowPolicy:
    def __init__(self, *, approval: object = False) -> None:
        self.approval = approval
        self.authorize_calls = 0

    def authorize(self, **_: object) -> bool:
        self.authorize_calls += 1
        return True

    def requires_approval(self, **_: object) -> object:
        return self.approval


class FakeResult:
    def __init__(self, scalar=None, first=None):
        self._scalar = scalar
        self._first = first

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar

    def first(self):
        return self._first


class FakeWriteSession:
    def __init__(self, results):
        self.results = list(results)
        self.rows = []
        self.flush_count = 0

    @contextmanager
    def begin_nested(self):
        yield

    def execute(self, _statement):
        return self.results.pop(0)

    def add(self, row):
        if hasattr(row, "id") and row.id is None:
            row.id = uuid4()
        self.rows.append(row)

    def flush(self):
        self.flush_count += 1


def test_quantity_registration_capability_is_a_canonical_identifier() -> None:
    assert Capability.QUANTITY_REGISTER.value == "inventory:quantity:register"
    assert is_known_capability("inventory:quantity:register")


def test_write_router_is_separately_constructed_and_not_operationally_registered() -> None:
    from app.api.v1.router import api_router
    from app.api.v1.routes.inventory_writes import build_inventory_write_router

    candidate = build_inventory_write_router(
        principal_dependency=lambda: None,
        session_dependency=lambda: None,
        write_policy_dependency=lambda: None,
        csrf_dependency=lambda: None,
    )
    assert any(route.path.endswith("/products") and "POST" in route.methods for route in candidate.routes)
    operational_routes = [
        route
        for included in api_router.routes
        for route in included.original_router.routes
    ]
    assert not any(route.path.endswith("/products") and "POST" in route.methods
                   for route in operational_routes)


def test_inventory_authorization_rejects_unknown_capability_before_policy_call() -> None:
    policy = AllowPolicy()
    with pytest.raises(AppError) as error:
        _authorize(policy, actor=uuid4(), capability="inventory:*", entity_type="inventory")
    assert error.value.status_code == 503
    assert policy.authorize_calls == 0


def test_inventory_authorization_fails_closed_without_policy() -> None:
    with pytest.raises(AppError) as error:
        _authorize(None, actor=uuid4(), capability=Capability.PRODUCTS_MANAGE, entity_type="product")
    assert error.value.status_code == 503


@pytest.mark.parametrize("result", [None, 1, "yes"])
def test_approval_policy_requires_an_explicit_boolean(result: object) -> None:
    with pytest.raises(AppError) as error:
        _approval_required(AllowPolicy(approval=result), "product_catalog_create")
    assert error.value.status_code == 503


def test_approval_policy_failure_is_sanitized() -> None:
    policy = Mock()
    policy.requires_approval.side_effect = RuntimeError("private policy implementation detail")
    with pytest.raises(AppError) as error:
        _approval_required(policy, "product_catalog_create")
    assert error.value.status_code == 503
    assert "private policy" not in str(error.value)


def test_product_specifications_reject_sensitive_keys_recursively() -> None:
    with pytest.raises(ValidationError):
        ProductCreate(category_id=uuid4(), name="Keyboard", specifications={
            "technical": [{"nested": {"employee_name": "fictional"}}],
        })


def test_product_specifications_reject_non_finite_numbers() -> None:
    with pytest.raises(ValidationError):
        ProductCreate(category_id=uuid4(), name="Keyboard", specifications={"weight": float("nan")})


def test_approval_reason_is_a_non_sensitive_machine_code() -> None:
    assert WorkflowApprovalDecision(decision="rejected", reason_code="policy.review_required")
    with pytest.raises(ValidationError):
        WorkflowApprovalDecision(decision="rejected", reason_code="Employee termination details")


def test_inventory_write_activation_requires_all_independent_release_evidence() -> None:
    with pytest.raises(InventoryWritesNotReady) as error:
        assert_inventory_writes_ready(InventoryWriteActivationEvidence())
    assert len(error.value.blockers) == 5
    assert error.value.blockers


def test_operational_inventory_router_builder_remains_closed_without_auth_approval() -> None:
    from app.api.v1.authentication_wiring import (
        build_approved_inventory_cookie_principal_override,
        build_approved_inventory_write_router,
    )

    with pytest.raises(AuthenticationNotReady):
        build_approved_inventory_write_router(
            database_session_dependency=lambda: None,
            configuration=AuthenticationRuntimeConfiguration(),
            evidence=AuthenticationActivationEvidence(),
            inventory_write_evidence=InventoryWriteActivationEvidence(),
            cookie_name="__Host-inventory-session",
            origins=None,
            csrf=None,
            csrf_header_max_bytes=1024,
            role_policy_dependency=lambda: None,
            write_policy_dependency=lambda: None,
            session_policy=None,
            clock=lambda: None,
        )
    with pytest.raises(AuthenticationNotReady):
        build_approved_inventory_cookie_principal_override(
            database_session_dependency=lambda: None,
            configuration=AuthenticationRuntimeConfiguration(),
            evidence=AuthenticationActivationEvidence(),
            cookie_name="__Host-inventory-session",
            role_policy_dependency=lambda: None,
            session_policy=None,
            clock=lambda: None,
        )


def test_registration_candidate_read_calculates_remaining_approved_quantity() -> None:
    from unittest.mock import MagicMock

    session = MagicMock()
    line = SimpleNamespace(id=uuid4(), product_id=uuid4(), quantity=Decimal("5.000"), unit="each")
    session.execute.return_value.all.return_value = [(line, uuid4(), "Fictional product", "Fictional location")]
    session.scalar.return_value = 2
    result = list_registration_candidates(session, tracking_mode="individual")
    assert len(result) == 1
    assert result[0].quantity == Decimal("5.000")
    assert result[0].remaining_quantity == Decimal("3.000")
    assert result[0].tracking_mode == "individual"


def test_finalization_candidates_expose_only_approved_registration_summary() -> None:
    from unittest.mock import MagicMock

    session = MagicMock()
    session.execute.side_effect = [
        MagicMock(all=MagicMock(return_value=[(uuid4(), "Fictional laptop")])),
        MagicMock(all=MagicMock(return_value=[(uuid4(), "Fictional cable", Decimal("4.000"), "each")])),
    ]
    result = list_registration_finalizations(session)
    assert [(item.tracking_mode, item.product_name, item.unit) for item in result] == [
        ("individual", "Fictional laptop", "asset"),
        ("quantity", "Fictional cable", "each"),
    ]


def test_product_creation_is_audited_and_stays_inactive_when_approval_is_required() -> None:
    actor_id, category_id = uuid4(), uuid4()
    category = SimpleNamespace(id=category_id, active=True)
    session = FakeWriteSession([FakeResult(), FakeResult(scalar=category), FakeResult()])
    audit_events = []
    result = create_product(
        session, actor_user_id=actor_id, idempotency_key="fictional-product-key",
        command=ProductCreate(category_id=category_id, name="Fictional keyboard"),
        policy=AllowPolicy(approval=True),
        audit_writer=lambda _session, event: audit_events.append(event),
    )
    product = next(row for row in session.rows if row.__class__.__name__ == "InventoryProduct")
    assert result.status == "pending_approval"
    assert product.active is False
    assert any(row.__class__.__name__ == "WorkflowApproval" for row in session.rows)
    assert audit_events[0].updated_values == {"product_active": False}
    assert session.flush_count >= 2


def test_receipt_creation_does_not_post_stock_before_approval_and_registration() -> None:
    actor_id, category_id, location_id, product_id = uuid4(), uuid4(), uuid4(), uuid4()
    category = SimpleNamespace(id=category_id, active=True, tracking_mode="quantity")
    location = SimpleNamespace(id=location_id, active=True)
    product = SimpleNamespace(id=product_id, active=True, category_id=category_id)
    session = FakeWriteSession([
        FakeResult(), FakeResult(scalar=location), FakeResult(scalar=product), FakeResult(scalar=category),
    ])
    audit_events = []
    command = ReceiptCreate(
        received_at=datetime(2026, 11, 26, tzinfo=timezone.utc), location_id=location_id,
        lines=[ReceiptLineCreate(product_id=product_id, quantity=Decimal("4"), unit="each", tracking_mode="quantity")],
    )
    result = create_receipt(
        session, actor_user_id=actor_id, idempotency_key="fictional-receipt-key",
        command=command, policy=AllowPolicy(approval=True),
        audit_writer=lambda _session, event: audit_events.append(event),
    )
    line = next(row for row in session.rows if row.__class__.__name__ == "ReceiptLine")
    assert result.status == "pending_approval"
    assert line.status == "pending"
    assert not any(row.__class__.__name__ in {"InventoryBalance", "InventoryMovement", "QuantityInventoryLot"}
                   for row in session.rows)
    assert audit_events[0].updated_values == {"receipt_status": "pending"}
