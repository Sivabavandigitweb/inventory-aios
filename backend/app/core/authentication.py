import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db_session
from app.models import Role, User, UserRole

logger = logging.getLogger(__name__)


class InvalidCredential(Exception):
    """The configured identity provider rejected the presented credential."""


class CredentialProviderUnavailable(Exception):
    """The configured identity provider cannot validate credentials right now."""


class RolePermissionPolicyUnavailable(Exception):
    """The configured role-to-permission policy cannot resolve access right now."""


class CredentialVerifier(Protocol):
    def verify_access_token(self, token: str) -> UUID:
        """Validate credentials and return the mapped local user UUID."""


class UnconfiguredCredentialVerifier:
    def verify_access_token(self, token: str) -> UUID:
        raise CredentialProviderUnavailable


class RolePermissionPolicy(Protocol):
    def permissions_for(self, role_codes: set[str]) -> frozenset[str]:
        """Resolve approved role codes to permissions; unknown roles grant nothing."""


class DenyAllRolePermissionPolicy:
    def permissions_for(self, role_codes: set[str]) -> frozenset[str]:
        return frozenset()


def get_credential_verifier() -> CredentialVerifier:
    return UnconfiguredCredentialVerifier()


def get_role_permission_policy() -> RolePermissionPolicy:
    return DenyAllRolePermissionPolicy()


def authenticate_principal(
    token: str,
    verifier: CredentialVerifier,
    session: Session,
    policy: RolePermissionPolicy,
) -> "Principal":
    if not _valid_bearer_value(token):
        raise AppError("INVALID_CREDENTIALS", "Credentials are invalid or expired.", 401)

    try:
        user_id = verifier.verify_access_token(token)
    except InvalidCredential:
        raise AppError("INVALID_CREDENTIALS", "Credentials are invalid or expired.", 401) from None
    except CredentialProviderUnavailable:
        raise AppError("AUTHENTICATION_UNAVAILABLE", "Authentication is not configured.", 503) from None
    except Exception:
        # Provider exceptions can contain the presented token; never log their text.
        logger.error("credential_verifier_unexpected_failure")
        raise AppError("INTERNAL_SERVER_ERROR", "An unexpected error occurred.", 500) from None

    if not isinstance(user_id, UUID):
        raise AppError("AUTHENTICATION_UNAVAILABLE", "Authentication is temporarily unavailable.", 503)

    try:
        user = session.get(User, user_id)
    except SQLAlchemyError:
        _rollback_failed_auth_lookup(session)
        raise AppError("AUTHENTICATION_UNAVAILABLE", "Authentication is temporarily unavailable.", 503) from None
    if user is None or getattr(user, "status", None) != "active":
        raise AppError("INVALID_CREDENTIALS", "Credentials are invalid or expired.", 401)
    if getattr(user, "id", None) != user_id:
        raise AppError("AUTHENTICATION_UNAVAILABLE", "Authentication is temporarily unavailable.", 503)

    now = datetime.now(timezone.utc)
    try:
        role_values = session.scalars(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user_id,
                UserRole.valid_from <= now,
                or_(UserRole.valid_to.is_(None), UserRole.valid_to > now),
            )
        ).all()
        if not isinstance(role_values, (list, tuple)) or not all(
            isinstance(role, str) and role and role == role.strip() for role in role_values
        ):
            raise AppError(
                "AUTHORIZATION_UNAVAILABLE", "Authorization is temporarily unavailable.", 503
            )
        role_codes = set(role_values)
    except SQLAlchemyError:
        _rollback_failed_auth_lookup(session)
        raise AppError("AUTHORIZATION_UNAVAILABLE", "Authorization is temporarily unavailable.", 503) from None

    try:
        permissions = policy.permissions_for(role_codes)
    except RolePermissionPolicyUnavailable:
        raise AppError("AUTHORIZATION_UNAVAILABLE", "Authorization is temporarily unavailable.", 503) from None
    except SQLAlchemyError:
        raise AppError("AUTHORIZATION_UNAVAILABLE", "Authorization is temporarily unavailable.", 503) from None
    except Exception:
        logger.error("role_permission_policy_unexpected_failure")
        raise AppError("INTERNAL_SERVER_ERROR", "An unexpected error occurred.", 500) from None

    if not _valid_permissions(permissions):
        raise AppError("AUTHORIZATION_UNAVAILABLE", "Authorization is temporarily unavailable.", 503)

    return Principal(
        user_id=user_id,
        permissions=permissions,
        roles=frozenset(role_codes),
    )


def _valid_bearer_value(token: object) -> bool:
    return (
        isinstance(token, str)
        and bool(token)
        and not any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in token
        )
    )


_PERMISSION_CODE = re.compile(r"[a-z][a-z0-9_-]*(?::[a-z][a-z0-9_-]*)*")


def _valid_permissions(permissions: object) -> bool:
    return (
        isinstance(permissions, frozenset)
        and all(
            isinstance(permission, str)
            and _PERMISSION_CODE.fullmatch(permission) is not None
            and "*" not in permission
            for permission in permissions
        )
    )


def _rollback_failed_auth_lookup(session: Session) -> None:
    try:
        session.rollback()
    except SQLAlchemyError:
        # The request-scoped dependency still closes the session in its finally block.
        pass


_bearer = HTTPBearer(auto_error=False)


def authenticated_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    verifier: CredentialVerifier = Depends(get_credential_verifier),
    policy: RolePermissionPolicy = Depends(get_role_permission_policy),
    session: Session = Depends(get_db_session),
) -> "Principal":
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AppError("AUTHENTICATION_REQUIRED", "Authentication is required.", 401)
    if not _valid_bearer_value(credentials.credentials):
        raise AppError("INVALID_CREDENTIALS", "Credentials are invalid or expired.", 401)
    return authenticate_principal(credentials.credentials, verifier, session, policy)


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    permissions: frozenset[str]
    roles: frozenset[str] = frozenset()



