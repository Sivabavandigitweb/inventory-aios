from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db_session
from app.models import Role, User, UserRole


class InvalidCredential(Exception):
    """The configured identity provider rejected the presented credential."""


class CredentialProviderUnavailable(Exception):
    """The configured identity provider cannot validate credentials right now."""


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
    try:
        user_id = verifier.verify_access_token(token)
    except InvalidCredential:
        raise AppError("INVALID_CREDENTIALS", "Credentials are invalid or expired.", 401) from None
    except CredentialProviderUnavailable:
        raise AppError("AUTHENTICATION_UNAVAILABLE", "Authentication is not configured.", 503) from None
    except Exception:
        raise AppError("AUTHENTICATION_UNAVAILABLE", "Authentication is temporarily unavailable.", 503) from None

    user = session.get(User, user_id)
    if user is None or user.status != "active":
        raise AppError("INVALID_CREDENTIALS", "Credentials are invalid or expired.", 401)

    now = datetime.now(timezone.utc)
    role_codes = set(session.scalars(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            UserRole.valid_from <= now,
            or_(UserRole.valid_to.is_(None), UserRole.valid_to > now),
        )
    ).all())
    return Principal(
        user_id=user_id,
        permissions=policy.permissions_for(role_codes),
        roles=frozenset(role_codes),
    )


_bearer = HTTPBearer(auto_error=False)


def authenticated_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    verifier: CredentialVerifier = Depends(get_credential_verifier),
    policy: RolePermissionPolicy = Depends(get_role_permission_policy),
    session: Session = Depends(get_db_session),
) -> "Principal":
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise AppError("AUTHENTICATION_REQUIRED", "Authentication is required.", 401)
    return authenticate_principal(credentials.credentials, verifier, session, policy)


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    permissions: frozenset[str]
    roles: frozenset[str] = frozenset()



