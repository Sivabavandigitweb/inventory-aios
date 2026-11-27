"""Transactional catalog, receiving, registration and approval operations.

All writes require an explicit policy object. The service is not wired into the
operational router; API composition must supply CSRF, session, capability and scope
checks and commit the request transaction before returning success.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.permission_catalog import is_known_capability
from app.models import (
    AssetCategory,
    AssetRegistrationEvent,
    AssetRegistrationRequest,
    IdempotencyRequest,
    InventoryBalance,
    InventoryMovement,
    InventoryProduct,
    Location,
    QuantityInventoryLot,
    QuantityRegistrationRequest,
    Receipt,
    ReceiptLine,
    Supplier,
    TrackedAsset,
    WorkflowApproval,
)
from app.schemas.inventory import (
    ProductCreate,
    ReceiptCreate,
    RegistrationApprovalRead,
    RegistrationCandidateRead,
    RegistrationFinalizationRead,
)
from app.services.audit import AuditEventInput, write_audit_event


class InventoryWritePolicy(Protocol):
    def authorize(self, *, actor_user_id: UUID, capability: str,
                  entity_type: str, entity_id: UUID | None) -> bool: ...
    def requires_approval(self, *, action: str) -> bool: ...
    def allows_self_approval(self, action: str) -> bool: ...


AuditWriter = Callable[[Session, AuditEventInput], object]


@dataclass(frozen=True, slots=True)
class WriteResult:
    id: UUID
    status: str
    replayed: bool = False


def list_registration_candidates(
    session: Session, *, tracking_mode: str,
) -> list[RegistrationCandidateRead]:
    if tracking_mode not in {"individual", "quantity"}:
        raise AppError("INVALID_TRACKING_MODE", "The registration tracking mode is invalid.", 422)
    request_model = AssetRegistrationRequest if tracking_mode == "individual" else QuantityRegistrationRequest
    try:
        rows = session.execute(
            select(ReceiptLine, Receipt.id, InventoryProduct.name, Location.name)
            .join(Receipt, ReceiptLine.receipt_id == Receipt.id)
            .join(InventoryProduct, ReceiptLine.product_id == InventoryProduct.id)
            .join(Location, Receipt.location_id == Location.id)
            .where(ReceiptLine.status == "approved", ReceiptLine.tracking_mode == tracking_mode)
            .order_by(Receipt.received_at, ReceiptLine.id)
        ).all()
        result: list[RegistrationCandidateRead] = []
        for line, receipt_id, product_name, location_name in rows:
            if tracking_mode == "individual":
                used = session.scalar(select(func.count(request_model.id)).where(
                    request_model.receipt_line_id == line.id,
                    request_model.status.not_in(("rejected", "cancelled")),
                )) or 0
                remaining = Decimal(line.quantity) - Decimal(used)
            else:
                used = session.scalar(select(func.coalesce(func.sum(request_model.quantity), 0)).where(
                    request_model.receipt_line_id == line.id,
                    request_model.status.not_in(("rejected", "cancelled")),
                )) or Decimal("0")
                remaining = Decimal(line.quantity) - Decimal(used)
            if remaining > 0:
                result.append(RegistrationCandidateRead(
                    id=line.id, receipt_id=receipt_id, product_id=line.product_id,
                    product_name=product_name, location_name=location_name,
                    tracking_mode=tracking_mode, quantity=Decimal(line.quantity),
                    unit=line.unit, remaining_quantity=remaining,
                ))
        return result
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "Registration candidates are unavailable.", 503) from None


def list_registration_approvals(
    session: Session, *, limit: int = 50, offset: int = 0,
) -> list[RegistrationApprovalRead]:
    if not 1 <= limit <= 100 or not 0 <= offset <= 10000:
        raise AppError("INVALID_PAGE", "The approval page is invalid.", 422)
    try:
        rows = session.execute(select(WorkflowApproval).where(
            WorkflowApproval.status == "pending",
            WorkflowApproval.entity_type.in_(
                ("product", "receiving", "asset_registration", "quantity_registration")
            ),
        ).order_by(WorkflowApproval.created_at, WorkflowApproval.id).limit(limit).offset(offset)).scalars()
        return [RegistrationApprovalRead(
            id=row.id, entity_type=row.entity_type, entity_id=row.entity_id,
            required_capability=row.required_capability, requested_by_id=row.requested_by_id,
            created_at=row.created_at,
        ) for row in rows]
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "Pending approvals are unavailable.", 503) from None


def list_registration_finalizations(session: Session) -> list[RegistrationFinalizationRead]:
    try:
        asset_rows = session.execute(
            select(AssetRegistrationRequest.id, InventoryProduct.name)
            .join(ReceiptLine, AssetRegistrationRequest.receipt_line_id == ReceiptLine.id)
            .join(InventoryProduct, ReceiptLine.product_id == InventoryProduct.id)
            .where(AssetRegistrationRequest.status == "approved")
            .order_by(AssetRegistrationRequest.created_at, AssetRegistrationRequest.id)
        ).all()
        quantity_rows = session.execute(
            select(QuantityRegistrationRequest.id, InventoryProduct.name,
                   QuantityRegistrationRequest.quantity, QuantityRegistrationRequest.unit)
            .join(ReceiptLine, QuantityRegistrationRequest.receipt_line_id == ReceiptLine.id)
            .join(InventoryProduct, ReceiptLine.product_id == InventoryProduct.id)
            .where(QuantityRegistrationRequest.status == "approved")
            .order_by(QuantityRegistrationRequest.created_at, QuantityRegistrationRequest.id)
        ).all()
        return [
            RegistrationFinalizationRead(
                request_id=request_id, tracking_mode="individual", product_name=product_name,
                quantity=Decimal("1"), unit="asset",
            )
            for request_id, product_name in asset_rows
        ] + [
            RegistrationFinalizationRead(
                request_id=request_id, tracking_mode="quantity", product_name=product_name,
                quantity=Decimal(quantity), unit=unit,
            )
            for request_id, product_name, quantity, unit in quantity_rows
        ]
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "Approved registrations are unavailable.", 503) from None


def _authorize(policy: InventoryWritePolicy | None, *, actor: UUID, capability: str,
               entity_type: str, entity_id: UUID | None = None) -> None:
    if not is_known_capability(capability):
        raise AppError("AUTHORIZATION_UNAVAILABLE", "Required inventory authorization is unavailable.", 503)
    if policy is None:
        raise AppError("WORKFLOW_UNAVAILABLE", "Required inventory authorization is unavailable.", 503)
    try:
        if policy.authorize(actor_user_id=actor, capability=capability,
                            entity_type=entity_type, entity_id=entity_id) is not True:
            raise AppError("FORBIDDEN", "This operation is not permitted.", 403)
    except AppError:
        raise
    except Exception:
        raise AppError("WORKFLOW_UNAVAILABLE", "Required inventory authorization is unavailable.", 503) from None


def _approval_required(policy: InventoryWritePolicy, action: str) -> bool:
    try:
        result = policy.requires_approval(action=action)
    except Exception:
        raise AppError("WORKFLOW_UNAVAILABLE", "Required approval policy is unavailable.", 503) from None
    if type(result) is not bool:
        raise AppError("WORKFLOW_UNAVAILABLE", "Required approval policy is unavailable.", 503)
    return result


def _self_approval_allowed(policy: InventoryWritePolicy | None, action: str) -> bool:
    """Fail closed unless an explicitly injected server policy permits the action."""
    checker = getattr(policy, "allows_self_approval", None) if policy is not None else None
    try:
        return callable(checker) and checker(action) is True
    except Exception:
        return False


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_key(key: str) -> None:
    if not isinstance(key, str) or not 1 <= len(key) <= 200 or not key.strip():
        raise AppError("INVALID_IDEMPOTENCY_KEY", "A valid idempotency key is required.", 422)


def _idempotent(
    session: Session, *, actor: UUID, scope: str, key: str, payload: object,
    create: Callable[[UUID], tuple[UUID, str]],
) -> WriteResult:
    """Claim and complete a write inside a savepoint; outer request commit is required."""
    _validate_key(key)
    fingerprint = _fingerprint(payload)

    def replay(existing: IdempotencyRequest) -> WriteResult:
        if existing.request_fingerprint != fingerprint:
            raise AppError("IDEMPOTENCY_CONFLICT", "The idempotency key was used for a different request.", 409)
        if existing.status != "succeeded" or existing.resource_id is None:
            raise AppError("REQUEST_IN_PROGRESS", "This request is already being processed.", 409)
        return WriteResult(id=existing.resource_id, status=existing.resource_type or "succeeded", replayed=True)

    try:
        with session.begin_nested():
            existing = session.execute(select(IdempotencyRequest).where(
                IdempotencyRequest.principal_id == actor,
                IdempotencyRequest.operation_scope == scope,
                IdempotencyRequest.idempotency_key == key,
            ).with_for_update()).scalar_one_or_none()
            if existing is not None:
                return replay(existing)
            request = IdempotencyRequest(
                id=uuid4(), principal_id=actor, operation_scope=scope, idempotency_key=key,
                request_fingerprint=fingerprint, status="processing",
            )
            session.add(request)
            session.flush()
            resource_id, resource_type = create(request.id)
            request.status = "succeeded"
            request.response_status = 201
            request.resource_type = resource_type
            request.resource_id = resource_id
            request.completed_at = datetime.now(timezone.utc)
            session.flush()
            return WriteResult(id=resource_id, status=resource_type)
    except AppError:
        raise
    except IntegrityError:
        # A concurrent transaction may have claimed this unique key. Its committed
        # result can be replayed; unrelated integrity failures remain sanitized.
        try:
            existing = session.execute(select(IdempotencyRequest).where(
                IdempotencyRequest.principal_id == actor,
                IdempotencyRequest.operation_scope == scope,
                IdempotencyRequest.idempotency_key == key,
            )).scalar_one_or_none()
        except SQLAlchemyError:
            existing = None
        if existing is not None:
            return replay(existing)
        raise AppError("INVENTORY_CONFLICT", "The inventory request conflicts with current data.", 409) from None
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The inventory write could not be completed.", 503) from None


def create_product(
    session: Session, *, actor_user_id: UUID, idempotency_key: str,
    command: ProductCreate, policy: InventoryWritePolicy | None,
    audit_writer: AuditWriter = write_audit_event,
) -> WriteResult:
    _authorize(policy, actor=actor_user_id, capability="products:manage", entity_type="inventory_product")
    if policy is None:
        raise AppError("WORKFLOW_UNAVAILABLE", "Product policy is unavailable.", 503)
    requires_approval = _approval_required(policy, "product_catalog_create")
    payload = command.model_dump(mode="json")

    def insert_product(request_id: UUID) -> tuple[UUID, str]:
        category = session.execute(select(AssetCategory).where(
            AssetCategory.id == command.category_id, AssetCategory.active.is_(True)
        ).with_for_update()).scalar_one_or_none()
        if category is None:
            raise AppError("INVALID_PRODUCT_CATEGORY", "An active product category is required.", 422)
        if command.sku is not None:
            duplicate = session.execute(select(InventoryProduct.id).where(
                InventoryProduct.sku == command.sku
            ).with_for_update()).first()
            if duplicate is not None:
                raise AppError("DUPLICATE_PRODUCT_SKU", "The product SKU is already in use.", 409)
        product = InventoryProduct(
            category_id=command.category_id, sku=command.sku, name=command.name,
            brand=command.brand, model=command.model, specifications=command.specifications,
            active=not requires_approval, idempotency_request_id=request_id,
        )
        session.add(product)
        session.flush()
        if requires_approval:
            session.add(WorkflowApproval(
                entity_type="product", entity_id=product.id,
                required_capability="approvals:decide:product_catalog", status="pending",
                requested_by_id=actor_user_id,
            ))
        audit_writer(session, AuditEventInput(
            actor_user_id=actor_user_id, action="inventory.product_created",
            entity_type="inventory_product", entity_id=product.id,
            metadata={"changed_fields": ["product_active"]},
            updated_values={"product_active": product.active},
        ))
        return product.id, "pending_approval" if requires_approval else "created"

    return _idempotent(session, actor=actor_user_id, scope="inventory.product.create",
                       key=idempotency_key, payload=payload, create=insert_product)


def create_receipt(
    session: Session, *, actor_user_id: UUID, idempotency_key: str,
    command: ReceiptCreate, policy: InventoryWritePolicy | None,
    audit_writer: AuditWriter = write_audit_event,
) -> WriteResult:
    _authorize(policy, actor=actor_user_id, capability="receipts:create", entity_type="receipt")
    if policy is None:
        raise AppError("WORKFLOW_UNAVAILABLE", "Receiving policy is unavailable.", 503)
    requires_approval = _approval_required(policy, "inventory_receiving")
    if command.received_at.tzinfo is None or command.received_at.utcoffset() is None:
        raise AppError("INVALID_RECEIVED_AT", "Receipt time must include a timezone.", 422)
    payload = command.model_dump(mode="json")

    def insert_receipt(request_id: UUID) -> tuple[UUID, str]:
        location = session.execute(select(Location).where(
            Location.id == command.location_id, Location.active.is_(True)
        ).with_for_update()).scalar_one_or_none()
        if location is None:
            raise AppError("INVALID_LOCATION", "An active receiving location is required.", 422)
        if command.supplier_id is not None:
            supplier = session.execute(select(Supplier).where(
                Supplier.id == command.supplier_id, Supplier.active.is_(True)
            ).with_for_update()).scalar_one_or_none()
            if supplier is None:
                raise AppError("INVALID_SUPPLIER", "An active supplier is required.", 422)
        for line in command.lines:
            product = session.execute(select(InventoryProduct).where(
                InventoryProduct.id == line.product_id, InventoryProduct.active.is_(True)
            ).with_for_update()).scalar_one_or_none()
            if product is None:
                raise AppError("INVALID_PRODUCT", "An active product is required for every receipt line.", 422)
            category = session.execute(select(AssetCategory).where(AssetCategory.id == product.category_id)).scalar_one()
            if category.tracking_mode != line.tracking_mode:
                raise AppError("TRACKING_MODE_MISMATCH", "Receipt tracking mode must match the product category.", 422)
            if line.tracking_mode == "individual" and line.quantity != line.quantity.to_integral_value():
                raise AppError("INDIVIDUAL_QUANTITY_INVALID", "Individual asset quantities must be whole units.", 422)

        receipt = Receipt(
            received_at=command.received_at, received_by_id=actor_user_id,
            location_id=command.location_id, supplier_id=command.supplier_id,
            external_reference=command.external_reference,
            idempotency_request_id=request_id,
        )
        session.add(receipt)
        session.flush()
        for line in command.lines:
            receipt_line = ReceiptLine(
                receipt_id=receipt.id, product_id=line.product_id, quantity=line.quantity,
                unit=line.unit, tracking_mode=line.tracking_mode,
                status="pending" if requires_approval else "approved",
            )
            session.add(receipt_line)
            session.flush()
            if requires_approval:
                session.add(WorkflowApproval(
                    entity_type="receiving", entity_id=receipt_line.id,
                    required_capability="approvals:decide:receiving", status="pending",
                    requested_by_id=actor_user_id,
                ))
        audit_writer(session, AuditEventInput(
            actor_user_id=actor_user_id, action="inventory.receipt_created",
            entity_type="receipt", entity_id=receipt.id,
            metadata={"changed_fields": ["receipt_status"]},
            updated_values={"receipt_status": "pending" if requires_approval else "approved"},
        ))
        return receipt.id, "pending_approval" if requires_approval else "received_pending_registration"

    return _idempotent(session, actor=actor_user_id, scope="inventory.receipt.create",
                       key=idempotency_key, payload=payload, create=insert_receipt)


def submit_asset_registration(
    session: Session, *, actor_user_id: UUID, idempotency_key: str,
    receipt_line_id: UUID, asset_number: str | None, serial_number: str | None,
    condition: str | None, policy: InventoryWritePolicy | None,
    audit_writer: AuditWriter = write_audit_event,
) -> WriteResult:
    _authorize(policy, actor=actor_user_id, capability="receipts:register_asset",
               entity_type="receipt_line", entity_id=receipt_line_id)
    payload = {"receipt_line_id": str(receipt_line_id), "asset_number": asset_number,
               "serial_number": serial_number, "condition": condition}

    def create_request(request_id: UUID) -> tuple[UUID, str]:
        line = session.execute(select(ReceiptLine).where(ReceiptLine.id == receipt_line_id)
                               .with_for_update()).scalar_one_or_none()
        if line is None or line.tracking_mode != "individual" or line.status != "approved":
            raise AppError("REGISTRATION_NOT_APPROVED", "An approved individual receipt line is required.", 409)
        count = session.scalar(select(func.count(AssetRegistrationRequest.id)).where(
            AssetRegistrationRequest.receipt_line_id == line.id,
            AssetRegistrationRequest.status.not_in(("rejected", "cancelled")),
        )) or 0
        if Decimal(count + 1) > Decimal(line.quantity):
            raise AppError("REGISTRATION_QUANTITY_EXCEEDED", "Registrations cannot exceed the approved receipt quantity.", 409)
        request = AssetRegistrationRequest(
            receipt_line_id=line.id, asset_number=asset_number, serial_number=serial_number,
            condition=condition, status="pending", submitted_by_id=actor_user_id,
            idempotency_request_id=request_id,
        )
        session.add(request)
        session.flush()
        session.add(WorkflowApproval(
            entity_type="asset_registration", entity_id=request.id,
            required_capability="approvals:decide:asset_registration", status="pending",
            requested_by_id=actor_user_id,
        ))
        audit_writer(session, AuditEventInput(
            actor_user_id=actor_user_id, action="inventory.asset_registration_submitted",
            entity_type="asset_registration_request", entity_id=request.id,
            metadata={"changed_fields": ["registration_status"]},
            updated_values={"registration_status": "pending"},
        ))
        return request.id, "pending_approval"

    return _idempotent(session, actor=actor_user_id, scope="inventory.asset.register.submit",
                       key=idempotency_key, payload=payload, create=create_request)


def submit_quantity_registration(
    session: Session, *, actor_user_id: UUID, idempotency_key: str,
    receipt_line_id: UUID, quantity: Decimal, unit: str,
    policy: InventoryWritePolicy | None, audit_writer: AuditWriter = write_audit_event,
) -> WriteResult:
    _authorize(policy, actor=actor_user_id, capability="inventory:quantity:register",
               entity_type="receipt_line", entity_id=receipt_line_id)
    payload = {"receipt_line_id": str(receipt_line_id), "quantity": str(quantity), "unit": unit}

    def create_request(request_id: UUID) -> tuple[UUID, str]:
        line = session.execute(select(ReceiptLine).where(ReceiptLine.id == receipt_line_id)
                               .with_for_update()).scalar_one_or_none()
        if line is None or line.tracking_mode != "quantity" or line.status != "approved" or line.unit != unit:
            raise AppError("REGISTRATION_NOT_APPROVED", "An approved quantity receipt line with the same unit is required.", 409)
        submitted = session.scalar(select(func.coalesce(func.sum(QuantityRegistrationRequest.quantity), 0)).where(
            QuantityRegistrationRequest.receipt_line_id == line.id,
            QuantityRegistrationRequest.status.not_in(("rejected", "cancelled")),
        )) or Decimal("0")
        if Decimal(submitted) + quantity > Decimal(line.quantity):
            raise AppError("REGISTRATION_QUANTITY_EXCEEDED", "Registrations cannot exceed the approved receipt quantity.", 409)
        request = QuantityRegistrationRequest(
            receipt_line_id=line.id, quantity=quantity, unit=unit, status="pending",
            submitted_by_id=actor_user_id, idempotency_request_id=request_id,
        )
        session.add(request)
        session.flush()
        session.add(WorkflowApproval(
            entity_type="quantity_registration", entity_id=request.id,
            required_capability="approvals:decide:quantity_registration", status="pending",
            requested_by_id=actor_user_id,
        ))
        audit_writer(session, AuditEventInput(
            actor_user_id=actor_user_id, action="inventory.quantity_registration_submitted",
            entity_type="quantity_registration_request", entity_id=request.id,
            metadata={"changed_fields": ["registration_status"]},
            updated_values={"registration_status": "pending"},
        ))
        return request.id, "pending_approval"

    return _idempotent(session, actor=actor_user_id, scope="inventory.quantity.register.submit",
                       key=idempotency_key, payload=payload, create=create_request)


def decide_registration_approval(
    session: Session, *, approval_id: UUID, actor_user_id: UUID, decision: str,
    reason_code: str | None, policy: InventoryWritePolicy | None,
    audit_writer: AuditWriter = write_audit_event,
) -> None:
    if decision not in {"approved", "rejected"}:
        raise AppError("INVALID_APPROVAL_DECISION", "The approval decision is invalid.", 422)
    try:
        with session.begin_nested():
            approval = session.execute(select(WorkflowApproval).where(
                WorkflowApproval.id == approval_id).with_for_update()).scalar_one_or_none()
            if approval is None:
                raise AppError("NOT_FOUND", "Approval request was not found.", 404)
            _authorize(policy, actor=actor_user_id, capability=approval.required_capability,
                       entity_type=approval.entity_type, entity_id=approval.entity_id)
            if approval.status != "pending":
                raise AppError("APPROVAL_ALREADY_DECIDED", "This approval request is no longer pending.", 409)
            if approval.requested_by_id == actor_user_id and not _self_approval_allowed(
                policy, approval.entity_type if approval.entity_type != "asset_registration" else "asset_registration"
            ):
                raise AppError("SELF_APPROVAL_FORBIDDEN", "A requester cannot decide their own request.", 403)
            previous = approval.status
            if approval.entity_type == "product":
                entity = session.execute(select(InventoryProduct).where(
                    InventoryProduct.id == approval.entity_id).with_for_update()).scalar_one_or_none()
                if entity is None:
                    raise AppError("WORKFLOW_INCONSISTENT", "The approval target is unavailable.", 409)
                entity.active = decision == "approved"
                field_name = "product_active"
                before: object = False
                after: object = entity.active
            elif approval.entity_type == "receiving":
                entity = session.execute(select(ReceiptLine).where(
                    ReceiptLine.id == approval.entity_id).with_for_update()).scalar_one_or_none()
                if entity is None:
                    raise AppError("WORKFLOW_INCONSISTENT", "The approval target is unavailable.", 409)
                before = entity.status
                entity.status = "approved" if decision == "approved" else "rejected"
                after = entity.status
                field_name = "receipt_status"
            elif approval.entity_type == "asset_registration":
                entity = session.execute(select(AssetRegistrationRequest).where(
                    AssetRegistrationRequest.id == approval.entity_id).with_for_update()).scalar_one_or_none()
                if entity is None:
                    raise AppError("WORKFLOW_INCONSISTENT", "The approval target is unavailable.", 409)
                before = entity.status
                entity.status = "approved" if decision == "approved" else "rejected"
                after = entity.status
                field_name = "registration_status"
            elif approval.entity_type == "quantity_registration":
                entity = session.execute(select(QuantityRegistrationRequest).where(
                    QuantityRegistrationRequest.id == approval.entity_id).with_for_update()).scalar_one_or_none()
                if entity is None:
                    raise AppError("WORKFLOW_INCONSISTENT", "The approval target is unavailable.", 409)
                before = entity.status
                entity.status = "approved" if decision == "approved" else "rejected"
                after = entity.status
                field_name = "registration_status"
            else:
                raise AppError("APPROVAL_UNAVAILABLE", "This approval workflow is not implemented.", 503)
            approval.status = decision
            approval.decided_by_id = actor_user_id
            approval.decided_at = datetime.now(timezone.utc)
            approval.decision_reason_code = reason_code
            audit_writer(session, AuditEventInput(
                actor_user_id=actor_user_id, action="inventory.approval_decided",
                entity_type="workflow_approval", entity_id=approval.id,
                metadata={"changed_fields": ["approval_status", field_name]},
                previous_values={"approval_status": previous, field_name: before},
                updated_values={"approval_status": decision, field_name: after},
            ))
            session.flush()
    except AppError:
        raise
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The approval decision could not be recorded.", 503) from None


def finalize_asset_registration(
    session: Session, *, request_id: UUID, actor_user_id: UUID,
    policy: InventoryWritePolicy | None, audit_writer: AuditWriter = write_audit_event,
) -> WriteResult:
    _authorize(policy, actor=actor_user_id, capability="receipts:register_asset",
               entity_type="asset_registration_request", entity_id=request_id)
    try:
        with session.begin_nested():
            request = session.execute(select(AssetRegistrationRequest).where(
                AssetRegistrationRequest.id == request_id).with_for_update()).scalar_one_or_none()
            if request is None:
                raise AppError("NOT_FOUND", "Registration request was not found.", 404)
            if request.status == "registered":
                asset = session.execute(select(TrackedAsset).where(
                    TrackedAsset.idempotency_request_id == request.idempotency_request_id
                )).scalar_one_or_none()
                if asset is None:
                    raise AppError("WORKFLOW_INCONSISTENT", "Completed registration data is unavailable.", 409)
                return WriteResult(id=asset.id, status="registered", replayed=True)
            if request.status != "approved":
                raise AppError("REGISTRATION_NOT_APPROVED", "Independent registration approval is required.", 403)
            approval = session.execute(select(WorkflowApproval).where(
                WorkflowApproval.entity_type == "asset_registration",
                WorkflowApproval.entity_id == request.id,
                WorkflowApproval.status == "approved",
            ).with_for_update()).scalar_one_or_none()
            if approval is None or (
                approval.decided_by_id == request.submitted_by_id
                and not _self_approval_allowed(policy, "asset_registration")
            ):
                raise AppError("REGISTRATION_NOT_APPROVED", "Independent registration approval is required.", 403)
            line = session.execute(select(ReceiptLine).where(
                ReceiptLine.id == request.receipt_line_id).with_for_update()).scalar_one_or_none()
            if line is None or line.status != "approved" or line.tracking_mode != "individual":
                raise AppError("WORKFLOW_INCONSISTENT", "The approved receipt line is unavailable.", 409)
            receipt = session.execute(select(Receipt).where(Receipt.id == line.receipt_id)
                                      .with_for_update()).scalar_one_or_none()
            product = session.execute(select(InventoryProduct).where(
                InventoryProduct.id == line.product_id, InventoryProduct.active.is_(True)
            ).with_for_update()).scalar_one_or_none()
            if receipt is None or product is None:
                raise AppError("WORKFLOW_INCONSISTENT", "Registration prerequisites are unavailable.", 409)
            completed = session.scalar(select(func.count(AssetRegistrationRequest.id)).where(
                AssetRegistrationRequest.receipt_line_id == line.id,
                AssetRegistrationRequest.status == "registered",
            )) or 0
            if Decimal(completed + 1) > Decimal(line.quantity):
                raise AppError("REGISTRATION_QUANTITY_EXCEEDED", "Registered assets exceed the approved receipt quantity.", 409)
            asset = TrackedAsset(
                product_id=line.product_id, receipt_line_id=line.id, location_id=receipt.location_id,
                asset_number=request.asset_number, serial_number=request.serial_number,
                lifecycle_status="available", condition=request.condition,
                idempotency_request_id=request.idempotency_request_id,
            )
            session.add(asset)
            session.flush()
            session.add(AssetRegistrationEvent(
                tracked_asset_id=asset.id, event_type="registered", actor_user_id=actor_user_id,
                details={},
            ))
            previous_request = request.status
            request.status = "registered"
            session.flush()
            if Decimal(completed + 1) == Decimal(line.quantity):
                previous_line = line.status
                line.status = "registered"
            else:
                previous_line = None
            old_values: dict[str, object] = {"registration_status": previous_request}
            new_values: dict[str, object] = {"registration_status": "registered", "lifecycle_status": "available"}
            changed_fields = ["registration_status", "lifecycle_status"]
            if previous_line is not None:
                old_values["receipt_status"] = previous_line
                new_values["receipt_status"] = line.status
                changed_fields.append("receipt_status")
            audit_writer(session, AuditEventInput(
                actor_user_id=actor_user_id, action="inventory.asset_registered",
                entity_type="tracked_asset", entity_id=asset.id,
                metadata={"changed_fields": changed_fields},
                previous_values=old_values, updated_values=new_values,
            ))
            session.flush()
            return WriteResult(id=asset.id, status="registered")
    except AppError:
        raise
    except IntegrityError:
        raise AppError("INVENTORY_CONFLICT", "The asset registration conflicts with existing inventory.", 409) from None
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The asset registration could not be completed.", 503) from None


def finalize_quantity_registration(
    session: Session, *, request_id: UUID, actor_user_id: UUID,
    policy: InventoryWritePolicy | None, audit_writer: AuditWriter = write_audit_event,
) -> WriteResult:
    _authorize(policy, actor=actor_user_id, capability="inventory:quantity:register",
               entity_type="quantity_registration_request", entity_id=request_id)
    try:
        with session.begin_nested():
            request = session.execute(select(QuantityRegistrationRequest).where(
                QuantityRegistrationRequest.id == request_id).with_for_update()).scalar_one_or_none()
            if request is None:
                raise AppError("NOT_FOUND", "Quantity registration request was not found.", 404)
            if request.status == "registered":
                lot = session.execute(select(QuantityInventoryLot).where(
                    QuantityInventoryLot.idempotency_request_id == request.idempotency_request_id
                )).scalar_one_or_none()
                if lot is None:
                    raise AppError("WORKFLOW_INCONSISTENT", "Completed quantity registration is unavailable.", 409)
                return WriteResult(id=lot.id, status="registered", replayed=True)
            if request.status != "approved":
                raise AppError("REGISTRATION_NOT_APPROVED", "Independent registration approval is required.", 403)
            approval = session.execute(select(WorkflowApproval).where(
                WorkflowApproval.entity_type == "quantity_registration",
                WorkflowApproval.entity_id == request.id,
                WorkflowApproval.status == "approved",
            ).with_for_update()).scalar_one_or_none()
            if approval is None or (
                approval.decided_by_id == request.submitted_by_id
                and not _self_approval_allowed(policy, "quantity_registration")
            ):
                raise AppError("REGISTRATION_NOT_APPROVED", "Independent registration approval is required.", 403)
            line = session.execute(select(ReceiptLine).where(
                ReceiptLine.id == request.receipt_line_id).with_for_update()).scalar_one_or_none()
            if line is None or line.status != "approved" or line.tracking_mode != "quantity" or line.unit != request.unit:
                raise AppError("WORKFLOW_INCONSISTENT", "The approved quantity receipt line is unavailable.", 409)
            receipt = session.execute(select(Receipt).where(Receipt.id == line.receipt_id)
                                      .with_for_update()).scalar_one_or_none()
            product = session.execute(select(InventoryProduct).where(
                InventoryProduct.id == line.product_id, InventoryProduct.active.is_(True)
            ).with_for_update()).scalar_one_or_none()
            if receipt is None or product is None:
                raise AppError("WORKFLOW_INCONSISTENT", "Registration prerequisites are unavailable.", 409)
            registered_before = session.scalar(select(func.coalesce(func.sum(
                QuantityRegistrationRequest.quantity), 0)).where(
                QuantityRegistrationRequest.receipt_line_id == line.id,
                QuantityRegistrationRequest.status == "registered",
            )) or Decimal("0")
            if Decimal(registered_before) + Decimal(request.quantity) > Decimal(line.quantity):
                raise AppError("REGISTRATION_QUANTITY_EXCEEDED", "Registered quantity exceeds the approved receipt quantity.", 409)

            statement = pg_insert(InventoryBalance).values(
                product_id=line.product_id, location_id=receipt.location_id, unit=request.unit,
                on_hand=request.quantity, reserved=Decimal("0"),
            ).on_conflict_do_update(
                index_elements=[InventoryBalance.product_id, InventoryBalance.location_id, InventoryBalance.unit],
                set_={"on_hand": InventoryBalance.on_hand + request.quantity, "updated_at": func.now()},
            ).returning(InventoryBalance.on_hand)
            new_on_hand = Decimal(session.execute(statement).scalar_one())
            old_on_hand = new_on_hand - Decimal(request.quantity)
            lot = QuantityInventoryLot(
                product_id=line.product_id, location_id=receipt.location_id,
                receipt_line_id=line.id, unit=request.unit, quantity=request.quantity,
                idempotency_request_id=request.idempotency_request_id,
            )
            session.add(lot)
            session.flush()
            session.add(InventoryMovement(
                product_id=line.product_id, location_id=receipt.location_id, unit=request.unit,
                quantity_delta=request.quantity, on_hand_delta=request.quantity,
                movement_type="receipt", actor_user_id=actor_user_id,
                idempotency_request_id=request.idempotency_request_id,
                reference_type="quantity_registration", reference_id=request.id,
            ))
            previous_request = request.status
            request.status = "registered"
            session.flush()
            registered_after = Decimal(registered_before) + Decimal(request.quantity)
            if registered_after == Decimal(line.quantity):
                previous_line = line.status
                line.status = "registered"
            else:
                previous_line = None
            old_values: dict[str, object] = {"registration_status": previous_request, "on_hand": old_on_hand}
            new_values: dict[str, object] = {"registration_status": "registered", "on_hand": new_on_hand}
            changed_fields = ["registration_status", "on_hand"]
            if previous_line is not None:
                old_values["receipt_status"] = previous_line
                new_values["receipt_status"] = line.status
                changed_fields.append("receipt_status")
            audit_writer(session, AuditEventInput(
                actor_user_id=actor_user_id, action="inventory.quantity_registered",
                entity_type="quantity_inventory_lot", entity_id=lot.id,
                metadata={"changed_fields": changed_fields},
                previous_values=old_values, updated_values=new_values,
            ))
            session.flush()
            return WriteResult(id=lot.id, status="registered")
    except AppError:
        raise
    except IntegrityError:
        raise AppError("INVENTORY_CONFLICT", "The quantity registration conflicts with current inventory.", 409) from None
    except SQLAlchemyError:
        raise AppError("DATABASE_UNAVAILABLE", "The quantity registration could not be completed.", 503) from None
