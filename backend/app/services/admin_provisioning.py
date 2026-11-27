"""Controlled administrator provisioning with a separate bootstrap audit actor."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.authentication import principal_for_local_user
from app.core.credential_verification import canonicalize_ascii_username
from app.core.password_hashing import PasswordHashBackend
from app.core.permission_catalog import Capability
from app.core.permission_policy import ExplicitRolePermissionPolicy
from app.models import (
    AdministratorBootstrapEvent,
    AuthSession,
    Role,
    User,
    UserPasswordCredential,
    UserRole,
)
from app.services.audit import AuditEventInput, write_audit_event

ADMIN_ROLE_CODES = {
    "super_admin": ("inventory_administrator", "security_administrator"),
    "system_admin": ("inventory_administrator",),
}


class AdministratorProvisioningRejected(RuntimeError):
    """Sanitized refusal; never includes input credentials or SQL details."""

    def __init__(self) -> None:
        super().__init__("Administrator provisioning could not be completed.")


def bootstrap_super_admin(
    session: Session,
    *,
    password: str,
    operator_identifier: str,
    authorization_reference: str,
    password_backend: PasswordHashBackend,
) -> UUID:
    """Atomically create the first admin without fabricating an authenticated user."""
    username = canonicalize_ascii_username("super_admin")
    if not _valid_attribution(operator_identifier, authorization_reference):
        raise AdministratorProvisioningRejected from None
    try:
        if session.scalar(select(AdministratorBootstrapEvent.id).where(
            AdministratorBootstrapEvent.action == "bootstrap"
        )) is not None:
            raise AdministratorProvisioningRejected from None
        if session.scalar(select(User.id).where(func.lower(User.username) == username)) is not None:
            raise AdministratorProvisioningRejected from None
        roles = _ensure_roles(session)
        user = User(
            username=username,
            email="super_admin@example.invalid",
            display_name="Fictional Super Administrator",
            status="active",
        )
        session.add(user)
        session.flush()
        session.add(UserPasswordCredential(
            user_id=user.id, password_hash=password_backend.hash(password), credential_version=1
        ))
        role_codes = ADMIN_ROLE_CODES[username]
        for role_code in role_codes:
            session.add(UserRole(user_id=user.id, role_id=roles[role_code].id, valid_from=datetime.now(UTC)))
        session.add(AdministratorBootstrapEvent(
            operator_identifier=operator_identifier,
            authorization_reference=authorization_reference,
            action="bootstrap",
            target_user_id=user.id,
            target_username=username,
            assigned_role_codes=list(role_codes),
        ))
        write_audit_event(session, AuditEventInput(
            actor_user_id=None,
            action="admin.bootstrap",
            entity_type="user",
            entity_id=user.id,
            change_source="system",
            metadata={"outcome": "success", "changed_fields": ["account", "authentication_state", "roles"]},
        ))
        session.flush()
        return user.id
    except AdministratorProvisioningRejected:
        raise
    except Exception:
        raise AdministratorProvisioningRejected from None


def provision_system_admin(
    session: Session,
    *,
    actor_user_id: UUID,
    password: str,
    password_backend: PasswordHashBackend,
) -> UUID:
    """Create the second admin only for a current, active super_admin principal."""
    username = canonicalize_ascii_username("system_admin")
    try:
        actor = session.get(User, actor_user_id)
        if actor is None or actor.status != "active" or actor.username != "super_admin":
            raise AdministratorProvisioningRejected from None
        principal = principal_for_local_user(actor_user_id, session, ExplicitRolePermissionPolicy())
        if Capability.USERS_PROVISION.value not in principal.permissions:
            raise AdministratorProvisioningRejected from None
        if session.scalar(select(User.id).where(func.lower(User.username) == username)) is not None:
            raise AdministratorProvisioningRejected from None
        roles = _ensure_roles(session)
        user = User(
            username=username,
            email="system_admin@example.invalid",
            display_name="Fictional System Administrator",
            status="active",
        )
        session.add(user)
        session.flush()
        session.add(UserPasswordCredential(
            user_id=user.id, password_hash=password_backend.hash(password), credential_version=1
        ))
        role_codes = ADMIN_ROLE_CODES[username]
        for role_code in role_codes:
            session.add(UserRole(user_id=user.id, role_id=roles[role_code].id, valid_from=datetime.now(UTC)))
        session.add(AdministratorBootstrapEvent(
            operator_identifier=str(actor_user_id),
            authorization_reference="capability:users:provision",
            action="provision",
            target_user_id=user.id,
            target_username=username,
            assigned_role_codes=list(role_codes),
        ))
        write_audit_event(session, AuditEventInput(
            actor_user_id=actor_user_id,
            action="admin.provision",
            entity_type="user",
            entity_id=user.id,
            metadata={"outcome": "success", "changed_fields": ["account", "authentication_state", "roles"]},
        ))
        session.flush()
        return user.id
    except AdministratorProvisioningRejected:
        raise
    except Exception:
        raise AdministratorProvisioningRejected from None


def deactivate_administrator(session: Session, *, actor_user_id: UUID, target_user_id: UUID) -> None:
    """Deactivate a target and revoke its sessions in the caller's transaction."""
    actor = _authorized_provisioner(session, actor_user_id)
    target = session.get(User, target_user_id)
    if target is None or target.username not in ADMIN_ROLE_CODES:
        raise AdministratorProvisioningRejected from None
    target.status = "inactive"
    now = datetime.now(UTC)
    session.query(AuthSession).filter(
        AuthSession.user_id == target_user_id, AuthSession.revoked_at.is_(None)
    ).update({AuthSession.revoked_at: now}, synchronize_session=False)
    session.flush()
    session.add(AdministratorBootstrapEvent(
        operator_identifier=str(actor.id), authorization_reference="capability:users:deactivate",
        action="deactivate", target_user_id=target.id, target_username=target.username,
        assigned_role_codes=[],
    ))
    write_audit_event(session, AuditEventInput(
        actor_user_id=actor.id, action="admin.deactivated", entity_type="user", entity_id=target.id,
        metadata={"outcome": "success", "changed_fields": ["status", "sessions"]},
    ))


def reset_administrator_password(
    session: Session, *, actor_user_id: UUID, target_user_id: UUID, password: str,
    password_backend: PasswordHashBackend,
) -> None:
    """Replace a credential, increment its version and revoke sessions atomically."""
    actor = _authorized_provisioner(session, actor_user_id)
    target = session.get(User, target_user_id)
    credential = session.get(UserPasswordCredential, target_user_id)
    if target is None or target.username not in ADMIN_ROLE_CODES or credential is None:
        raise AdministratorProvisioningRejected from None
    old_version = credential.credential_version
    credential.password_hash = password_backend.hash(password)
    credential.password_changed_at = datetime.now(UTC)
    credential.credential_version = old_version + 1
    now = datetime.now(UTC)
    session.query(AuthSession).filter(
        AuthSession.user_id == target_user_id, AuthSession.revoked_at.is_(None)
    ).update({AuthSession.revoked_at: now}, synchronize_session=False)
    session.flush()
    session.add(AdministratorBootstrapEvent(
        operator_identifier=str(actor.id), authorization_reference="capability:credentials:recover",
        action="credential_reset", target_user_id=target.id, target_username=target.username,
        assigned_role_codes=[],
    ))
    write_audit_event(session, AuditEventInput(
        actor_user_id=actor.id, action="admin.credential_reset", entity_type="user", entity_id=target.id,
        metadata={"outcome": "success", "changed_fields": ["authentication_state", "sessions"]},
    ))


def _authorized_provisioner(session: Session, actor_user_id: UUID) -> User:
    actor = session.get(User, actor_user_id)
    if actor is None or actor.status != "active" or actor.username != "super_admin":
        raise AdministratorProvisioningRejected from None
    principal = principal_for_local_user(actor_user_id, session, ExplicitRolePermissionPolicy())
    required = {Capability.USERS_PROVISION.value, Capability.USERS_DEACTIVATE.value,
                Capability.CREDENTIALS_RECOVER.value}
    if not required <= principal.permissions:
        raise AdministratorProvisioningRejected from None
    return actor


def _ensure_roles(session: Session) -> dict[str, Role]:
    names = {
        "inventory_administrator": ("Inventory Administrator", "Explicit inventory operation capabilities."),
        "security_administrator": ("Security Administrator", "Restricted account and security capabilities."),
    }
    rows = {role.code: role for role in session.scalars(select(Role).where(
        Role.code.in_(names)
    )).all()}
    for code, (name, description) in names.items():
        if code not in rows:
            role = Role(code=code, name=name, description=description)
            session.add(role)
            rows[code] = role
    session.flush()
    return rows


def _valid_attribution(operator_identifier: str, authorization_reference: str) -> bool:
    return (
        isinstance(operator_identifier, str) and operator_identifier.strip() == operator_identifier
        and 1 <= len(operator_identifier) <= 120
        and isinstance(authorization_reference, str)
        and authorization_reference.strip() == authorization_reference
        and 1 <= len(authorization_reference) <= 160
    )