"""Target-guarded fictional administrator provisioning for restore-check only."""
from __future__ import annotations
import argparse
import getpass
import os
import sys
from pathlib import Path
from uuid import UUID

BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from sqlalchemy import create_engine, func, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from app.core.argon2_passwords import Argon2CostParameters, Argon2VerificationLimits, Argon2idPasswordBackend  # noqa: E402
from app.core.config import get_migration_settings  # noqa: E402
from app.core.password_hashing import InvalidStoredPasswordHash  # noqa: E402
from app.models import User, UserPasswordCredential  # noqa: E402
from app.services.admin_provisioning import (  # noqa: E402
    AdministratorProvisioningRejected, bootstrap_super_admin, deactivate_administrator,
    provision_system_admin, reset_administrator_password,
)


def backend():
    return Argon2idPasswordBackend(
        hash_parameters=Argon2CostParameters(8192, 2, 1, 16, 32),
        verification_limits=Argon2VerificationLimits(65536, 3, 4, 32, 64, 1024, 4096),
    )


def hidden_confirm(label: str) -> str:
    first = getpass.getpass(f"{label} password (hidden): ")
    if not first or first != getpass.getpass("Repeat password (hidden): "):
        raise ValueError("Password confirmation failed.")
    return first


def verify_super_admin(session: Session, hasher: Argon2idPasswordBackend) -> UUID:
    username = input("Provisioning authority username: ")
    if username.strip() != "super_admin":
        raise AdministratorProvisioningRejected from None
    supplied = getpass.getpass("super_admin password (hidden): ")
    user = session.scalar(select(User).where(func.lower(User.username) == "super_admin"))
    credential = session.get(UserPasswordCredential, user.id) if user else None
    if not user or user.status != "active" or not credential:
        raise AdministratorProvisioningRejected from None
    try:
        if not hasher.verify(supplied, credential.password_hash):
            raise AdministratorProvisioningRejected from None
    except (InvalidStoredPasswordHash, Exception):
        raise AdministratorProvisioningRejected from None
    return user.id


def main() -> int:
    parser = argparse.ArgumentParser(description="Fictional restore-check administrator provisioning only.")
    parser.add_argument("--operation", required=True, choices=("bootstrap", "provision", "deactivate", "reset"))
    parser.add_argument("--operator-id", help="Bootstrap operator identifier; not a secret.")
    parser.add_argument("--authorization-reference", help="Bootstrap authorization reference; not a secret.")
    parser.add_argument("--target-user-id", type=UUID)
    args = parser.parse_args()
    if args.operation == "bootstrap" and (not args.operator_id or not args.authorization_reference):
        print("Bootstrap requires --operator-id and --authorization-reference.", file=sys.stderr)
        return 2
    if args.operation in {"deactivate", "reset"} and not args.target_user_id:
        print("This operation requires --target-user-id.", file=sys.stderr)
        return 2
    config = get_migration_settings()
    if not config.migration_database_url:
        print("Migration database configuration is absent.", file=sys.stderr)
        return 2
    url = make_url(config.migration_database_url)
    if (url.host, url.port, url.database, url.username, url.password) != (
        "localhost", 5432, "inventory_aios_restore_check", "inventory_aios_migrator", None
    ):
        print("Refusing configured target or embedded password.", file=sys.stderr)
        return 2
    hasher = backend()
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
    try:
        with engine.connect() as connection, connection.begin():
            connection.execute(text("SET LOCAL ROLE inventory_aios_owner"))
            identity = connection.execute(text(
                "SELECT current_database(), session_user, current_user, inet_server_port(), "
                "(SELECT version_num FROM public.alembic_version)"
            )).one()
        if identity != ("inventory_aios_restore_check", "inventory_aios_migrator", "inventory_aios_owner", 5432, "d2a8f4c1b790"):
            print("Refusing database identity or revision.", file=sys.stderr)
            return 2
        with Session(engine, expire_on_commit=False) as session, session.begin():
            session.execute(text("SET LOCAL ROLE inventory_aios_owner"))
            if args.operation == "bootstrap":
                bootstrap_super_admin(
                    session, password=hidden_confirm("Fictional super_admin"),
                    operator_identifier=args.operator_id,
                    authorization_reference=args.authorization_reference,
                    password_backend=hasher,
                )
            else:
                actor = verify_super_admin(session, hasher)
                if args.operation == "provision":
                    provision_system_admin(session, actor_user_id=actor,
                                           password=hidden_confirm("Fictional system_admin"), password_backend=hasher)
                elif args.operation == "deactivate":
                    deactivate_administrator(session, actor_user_id=actor, target_user_id=args.target_user_id)
                else:
                    reset_administrator_password(
                        session, actor_user_id=actor, target_user_id=args.target_user_id,
                        password=hidden_confirm("Replacement"), password_backend=hasher,
                    )
        print("Operation committed. Credential material was not displayed.")
        return 0
    except Exception:
        print("Administrator operation failed and was rolled back.", file=sys.stderr)
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())