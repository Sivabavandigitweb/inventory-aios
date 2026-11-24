import re
from collections.abc import Mapping
from dataclasses import dataclass, field
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


_METADATA_KEYS = {"request_id", "changed_fields", "outcome"}
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")
_FIELD_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REQUEST_ID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_SENSITIVE_FIELD_NAMES = {
    "password", "password_hash", "token", "access_token", "refresh_token",
    "secret", "credential", "authorization",
}


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
    )


def write_audit_event(session: Session, event: AuditEventInput) -> AuditEvent:
    """Stage and flush an event in the caller's transaction; never commit or suppress errors."""
    row = build_audit_event(event)
    session.add(row)
    session.flush()
    return row
