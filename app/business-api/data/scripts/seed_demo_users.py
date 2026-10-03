"""Create persisted login identities for selected customers.

Every selected customer receives a `users` row built from their own real
`customers.email`, sharing one operator-supplied password so the same
credential can demo multiple real customers. The password is never accepted
as a command-line argument; it must be set in the `DEMO_USER_PASSWORD`
environment variable so it never appears in process listings or shell
history.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from pwdlib import PasswordHash
from sqlmodel import Session, select

from banking_shared.identity_models import CustomerUser, IdentityAudit, Operator, Role, UserRole, utc_now

DATA_DIR = Path(__file__).resolve().parents[1]
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

from database import create_session
from models import Customer, User
from scripts.shared import parse_customer_ids

DEMO_USER_PASSWORD_ENV = "DEMO_USER_PASSWORD"
ADMIN_BOOTSTRAP_PASSWORD_ENV = "ADMIN_BOOTSTRAP_PASSWORD"
password_hasher = PasswordHash.recommended()


@dataclass(frozen=True)
class SeedUsersResult:
    seeded_customer_ids: tuple[str, ...]
    skipped_customer_ids: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create or refresh real, persisted users for selected customer IDs, all "
            f"sharing the password supplied through {DEMO_USER_PASSWORD_ENV}."
        )
    )
    parser.add_argument(
        "--customer-ids",
        required=True,
        help="Comma-separated customer IDs to seed, for example C001,C002,C003.",
    )
    parser.add_argument(
        "--locale",
        help=(
            "Optional locale assigned to every selected user. By default, locale is "
            "inferred from customer country (Brazil/Brasil: pt; all others: es)."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Output path for the non-secret manifest (defaults under DATA_ARTIFACTS_DIR).",
    )
    return parser.parse_args()


def load_shared_password() -> str:
    password = os.environ.get(DEMO_USER_PASSWORD_ENV, "").strip()
    if not password:
        raise ValueError(f"{DEMO_USER_PASSWORD_ENV} must be set and non-empty")
    ensure_separate_password(password)
    return password


def ensure_separate_password(password: str) -> None:
    administrator_password = os.environ.get(ADMIN_BOOTSTRAP_PASSWORD_ENV)
    if administrator_password is not None and password == administrator_password:
        raise ValueError("Administrator and customer passwords must differ")


def default_manifest_path(customer_ids: tuple[str, ...]) -> Path:
    artifacts_dir = Path(os.environ.get("DATA_ARTIFACTS_DIR", "").strip() or (DATA_DIR / "artifacts"))
    digest = hashlib.sha256(",".join(sorted(customer_ids)).encode("utf-8")).hexdigest()[:8]
    return artifacts_dir / f"demo_users_manifest_customers-{len(customer_ids)}-{digest}.json"


def locale_for_customer(customer: Customer, locale_override: str | None) -> str:
    if locale_override:
        return locale_override
    if (customer.country or "").strip().casefold() in {"brazil", "brasil"}:
        return "pt"
    return "es"


def seed_users(
    customer_ids: tuple[str, ...], locale: str | None, password: str
) -> SeedUsersResult:
    ensure_separate_password(password)
    with create_session() as session:
        customers = {
            customer.customer_id: customer
            for customer in session.exec(
                select(Customer).where(Customer.customer_id.in_(customer_ids))
            ).all()
        }
        missing_customer_ids = [
            customer_id for customer_id in customer_ids if customer_id not in customers
        ]
        valid_customer_ids = tuple(
            customer_id for customer_id in customer_ids if customer_id in customers
        )

        if valid_customer_ids:
            if session.exec(select(Role).where(Role.name == "customer")).first() is None:
                raise ValueError("Apply identity migrations before provisioning customers")
            for customer_id in valid_customer_ids:
                _seed_customer(session, customers[customer_id], locale, password)
        session.commit()
        return SeedUsersResult(valid_customer_ids, tuple(missing_customer_ids))


def _seed_customer(
    session: Session, customer: Customer, locale: str | None, password: str
) -> None:
    mapping = session.exec(select(CustomerUser).where(
        CustomerUser.customer_id == customer.customer_id
    )).first()
    user = None
    if mapping is not None:
        user = session.exec(select(User).where(
            User.id == mapping.user_id
        ).with_for_update()).first()
        assignment = session.get(UserRole, mapping.user_id)
        if (
            user is None
            or assignment is None
            or session.get(Role, assignment.role_id) is None
            or session.get(Role, assignment.role_id).name != "customer"
            or session.get(Operator, mapping.user_id) is not None
        ):
            raise ValueError("Invalid customer identity association")
    email = customer.email.strip().lower()
    collision = session.exec(select(User).where(User.email == email)).first()
    if collision is not None and (user is None or collision.id != user.id):
        raise ValueError("Customer email already belongs to another identity")
    name = " ".join(
        component.strip()
        for component in (customer.first_name, customer.last_name)
        if component and component.strip()
    ) or None
    now = utc_now()
    if user is None:
        user = User(email=email, name=name, password_hash=password_hasher.hash(password),
                    locale=locale_for_customer(customer, locale), status="active")
        session.add(user)
        session.flush()
        session.add(CustomerUser(user_id=user.id, customer_id=customer.customer_id))
        role = session.exec(select(Role).where(Role.name == "customer")).one()
        session.add(UserRole(user_id=user.id, role_id=role.id))
    else:
        user.email = email
        user.name = name
        user.password_hash = password_hasher.hash(password)
        user.locale = locale_for_customer(customer, locale)
        user.status = "active"
        user.identity_version += 1
        user.updated_at = now
        session.add(user)
    session.add(IdentityAudit(target_id=user.id, action="customer_migrate"))
    session.flush()


def build_manifest(customer_ids: tuple[str, ...]) -> list[dict[str, str]]:
    with create_session() as session:
        seeded_users = session.exec(
            select(User, CustomerUser).join(CustomerUser).where(
                CustomerUser.customer_id.in_(customer_ids)
            ).order_by(CustomerUser.customer_id)
        ).all()
        return [
            {
                "user_id": user.id,
                "customer_id": mapping.customer_id,
                "email": user.email,
                "locale": user.locale,
                "status": user.status,
            }
            for user, mapping in seeded_users
        ]


def main() -> None:
    args = parse_args()
    customer_ids = parse_customer_ids(args.customer_ids)
    password = load_shared_password()

    result = seed_users(customer_ids, args.locale, password)
    manifest_entries = build_manifest(result.seeded_customer_ids)

    manifest_path = args.manifest or default_manifest_path(customer_ids)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest_entries, indent=2), encoding="utf-8")

    print(f"Seeded {len(manifest_entries)} user(s). Manifest written to {manifest_path}")
    if result.skipped_customer_ids:
        print(
            "Skipped unknown customer ID(s): "
            + ", ".join(result.skipped_customer_ids)
        )


if __name__ == "__main__":
    main()
