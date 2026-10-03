"""Explicit one-time administrator bootstrap; never invoked by application startup."""
from __future__ import annotations

import argparse
import os
from collections.abc import Mapping
from getpass import getpass

from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, create_engine, select

from banking_shared.identity_models import IdentityAudit, Role, User, UserRole
from identity.schemas import AdminBootstrap
from identity.service import IdentityService
from identity.settings import Settings


def bootstrap_admin(session: Session, service: IdentityService, request: AdminBootstrap) -> str:
    # Serializing on the controlled catalog prevents concurrent first-admin creation.
    role = session.exec(select(Role).where(Role.name == "admin").with_for_update()).first()
    if role is None:
        raise ValueError("Apply identity migrations before bootstrapping")
    if session.exec(select(UserRole).where(UserRole.role_id == role.id)).first():
        raise ValueError("An administrator already exists")
    if session.exec(select(User).where(User.email == request.email)).first():
        raise ValueError("Email already belongs to an identity")
    user = User(email=request.email, password_hash=service.passwords.hash(
        request.password.get_secret_value()), locale=request.locale, name=request.name, status="active")
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role_id=role.id))
    session.add(IdentityAudit(actor_id=user.id, target_id=user.id, action="admin_bootstrap"))
    session.commit()
    return user.id


def load_bootstrap_request(
    args: argparse.Namespace, environment: Mapping[str, str],
) -> AdminBootstrap:
    if args.credentials_from_env:
        if args.email is not None:
            raise ValueError("Choose either environment credentials or --email")
        email = environment.get("ADMIN_BOOTSTRAP_EMAIL", "")
        password = environment.get("ADMIN_BOOTSTRAP_PASSWORD", "")
        if not email.strip() or not password.strip():
            raise ValueError("Explicit administrator environment credentials are required")
    else:
        if not args.email:
            raise ValueError("Explicit administrator email is required")
        email = args.email
        password = getpass("New administrator password: ")
        if password != getpass("Confirm password: "):
            raise ValueError("Passwords do not match")
    customer_password = environment.get("DEMO_USER_PASSWORD", "").strip()
    if customer_password and password == customer_password:
        raise ValueError("Administrator and customer passwords must differ")
    return AdminBootstrap(email=email, password=password, locale=args.locale, name=args.name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Explicit first-administrator bootstrap")
    parser.add_argument("--email")
    parser.add_argument(
        "--credentials-from-env", action="store_true",
        help="Explicitly use ADMIN_BOOTSTRAP_EMAIL and ADMIN_BOOTSTRAP_PASSWORD",
    )
    parser.add_argument("--locale", choices=("en", "es", "pt"), required=True)
    parser.add_argument("--name")
    parser.add_argument("--confirm-bootstrap", action="store_true", required=True)
    args, unknown = parser.parse_known_args()
    if unknown:
        parser.error("Unsupported bootstrap arguments")
    engine: Engine | None = None
    try:
        request = load_bootstrap_request(args, os.environ)
        settings = Settings()
        engine = create_engine(settings.database_url.get_secret_value(),
                               connect_args={"connect_timeout": 3})
        with Session(engine) as session:
            bootstrap_admin(session, IdentityService(settings), request)
    except ValidationError:
        parser.exit(1, "Invalid bootstrap input or Auth configuration\n")
    except SQLAlchemyError:
        parser.exit(1, "Auth database unavailable or identity conflict; no bootstrap completed\n")
    except ValueError:
        parser.exit(1, "Bootstrap rejected; verify credentials, migration and first-admin prerequisites\n")
    finally:
        if engine is not None:
            engine.dispose()
    print("Administrator bootstrapped")


if __name__ == "__main__":
    main()
