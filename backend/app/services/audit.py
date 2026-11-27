import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditEvent


class AuditEventValidationError(ValueError):
    """Raised when an audit event is incomplete or contains unsafe metadata."""


@dataclass(frozen=True)
class AuditEventInput:
    actor_user_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID
    change_source: str = "user"
    metadata: Mapping[str, object] = field(default_factory=dict)
    previous_values: Mapping[str, object] | None = None
    updated_values: Mapping[str, object] | None = None


_METADATA_KEYS = {"request_id", "changed_fields", "outcome"}
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")
_FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REQUEST_ID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_SENSITIVE_FIELD_NAMES = {
    "password", "password_hash", "token", "access_token", "refresh_token",
    "secret", "credential", "authorization",
}
_AUDIT_VALUE_FIELDS = frozenset({
    "lifecycle_status", "allocation_status", "approval_status", "clearance_status",
    "verification_status", "receipt_status", "registration_status", "product_active",
    "condition", "repair_status", "disposal_status", "disposition_status",
    "location_id", "quantity", "reserved", "returned_quantity", "on_hand", "quarantined",
})
_AUDIT_VALUE_ENUMS = {
    "lifecycle_status": {"available", "allocated", "repair", "damaged", "disposed"},
    "allocation_status": {"pending", "approved", "rejected", "issued", "cancelled", "partially_returned", "returned"},
    "approval_status": {"pending", "approved", "rejected", "cancelled"},
    "clearance_status": {"pending", "in_progress", "completed", "cancelled"},
    "verification_status": {"unverified", "verified", "exceptions"},
    "receipt_status": {"pending", "approved", "rejected", "registered"},
    "registration_status": {"pending", "approved", "rejected", "registered", "cancelled"},
    "condition": {"good", "repair", "damaged", "unknown"},
    "repair_status": {"reported", "in_progress", "completed", "cancelled"},
    "disposal_status": {"pending", "approved", "rejected", "completed", "cancelled"},
    "disposition_status": {"pending", "approved", "rejected", "completed"},
}
_AUDIT_NUMERIC_FIELDS = frozenset({"quantity", "reserved", "returned_quantity", "on_hand", "quarantined"})


def _validated_values(values: Mapping[str, object] | None) -> dict[str, object] | None:
    if values is None:
        return None
    if not isinstance(values, Mapping) or len(values) > 20:
        raise AuditEventValidationError("Audit values must be a small mapping.")
    safe: dict[str, object] = {}
    for key, value in values.items():
        if key not in _AUDIT_VALUE_FIELDS:
            raise AuditEventValidationError("Audit values contain an unsupported field.")
        if isinstance(value, UUID):
            value = str(value)
        if value is None:
            raise AuditEventValidationError("Audit values cannot contain null values.")
        if type(value) not in {str, int, float, bool} and not isinstance(value, (Decimal, UUID)):
            raise AuditEventValidationError("Audit values contain an unsupported value.")
        if key in _AUDIT_NUMERIC_FIELDS:
            if type(value) not in {int, float} and not isinstance(value, Decimal):
                raise AuditEventValidationError("Audit numeric values have an invalid type.")
            numeric_value = Decimal(str(value))
            if (not numeric_value.is_finite() or numeric_value < 0
                    or numeric_value > Decimal("99999999999.999")
                    or max(-numeric_value.as_tuple().exponent, 0) > 3):
                raise AuditEventValidationError("Audit values contain an invalid number.")
        if key == "product_active" and type(value) is not bool:
            raise AuditEventValidationError("Audit product state is invalid.")
        if key in _AUDIT_VALUE_ENUMS and (type(value) is not str or value not in _AUDIT_VALUE_ENUMS[key]):
            raise AuditEventValidationError("Audit state value is invalid.")
        if key == "location_id" and (type(value) is not str or not re.fullmatch(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", value
        )):
            raise AuditEventValidationError("Audit location value is invalid.")
        if isinstance(value, str) and len(value) > 120:
            raise AuditEventValidationError("Audit values contain an oversized value.")
        safe[key] = str(value) if isinstance(value, Decimal) else value
    return safe


def _validated_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(metadata, Mapping):
        raise AuditEventValidationError("Audit metadata must be a mapping.")
    if set(metadata) - _METADATA_KEYS:
        raise AuditEventValidationError("Audit metadata contains an unsupported field.")

    safe: dict[str, object] = {}
    for key, value in metadata.items():
        if key == "request_id":
            if not isinstance(value, str) or not _REQUEST_ID.fullmatch(value):
                raise AuditEventValidationError("Audit request_id is invalid.")
            safe[key] = value
        elif key == "changed_fields":
            if not isinstance(value, (list, tuple)) or len(value) > 20:
                raise AuditEventValidationError("Audit changed_fields is invalid.")
            if any(
                not isinstance(name, str)
                or not _FIELD_NAME.fullmatch(name)
                or any(term in name for term in _SENSITIVE_FIELD_NAMES)
                for name in value
            ) or len(set(value)) != len(value):
                raise AuditEventValidationError("Audit changed_fields contains an unsafe value.")
            safe[key] = list(value)
        elif key == "outcome":
            if not isinstance(value, str) or value not in {"success", "failure"}:
                raise AuditEventValidationError("Audit outcome is invalid.")
            safe[key] = value
    return safe


def build_audit_event(event: AuditEventInput) -> AuditEvent:
    """Validate and construct an event without storing confidential business values."""
    if not isinstance(event.actor_user_id, UUID) and event.actor_user_id is not None:
        raise AuditEventValidationError("Audit actor must be a local user UUID.")
    if not isinstance(event.change_source, str) or event.change_source not in {"user", "system", "import"}:
        raise AuditEventValidationError("Audit change_source is invalid.")
    if event.change_source == "user" and event.actor_user_id is None:
        raise AuditEventValidationError("User-originated audit events require an actor.")
    if not isinstance(event.entity_id, UUID):
        raise AuditEventValidationError("Audit entity_id must be a UUID.")
    if not isinstance(event.action, str) or not _IDENTIFIER.fullmatch(event.action):
        raise AuditEventValidationError("Audit action is invalid.")
    if not isinstance(event.entity_type, str) or not _IDENTIFIER.fullmatch(event.entity_type):
        raise AuditEventValidationError("Audit entity_type is invalid.")

    return AuditEvent(
        actor_user_id=event.actor_user_id,
        action=event.action,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        change_source=event.change_source,
        event_metadata=_validated_metadata(event.metadata),
        previous_values=_validated_values(event.previous_values),
        updated_values=_validated_values(event.updated_values),
    )


def write_audit_event(session: Session, event: AuditEventInput) -> AuditEvent:
    """Stage and flush an event in the caller's transaction; never commit or suppress errors."""
    row = build_audit_event(event)
    session.add(row)
    session.flush()
    return row
