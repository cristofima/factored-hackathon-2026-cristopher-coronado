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
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import select

DATA_DIR = Path(__file__).resolve().parents[1]
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

from database import create_session
from models import Customer, User
from scripts.shared import parse_customer_ids

DEMO_USER_PASSWORD_ENV = "DEMO_USER_PASSWORD"
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
    return password


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

        for customer_id in valid_customer_ids:
            email = customers[customer_id].email.strip().lower()
            user = User(
                customer_id=customer_id,
                email=email,
                password_hash=password_hasher.hash(password),
                locale=locale_for_customer(customers[customer_id], locale),
            )
            statement = insert(User).values(**user.model_dump())
            session.exec(
                statement.on_conflict_do_update(
                    index_elements=["customer_id"],
                    set_={
                        "email": statement.excluded.email,
                        "password_hash": statement.excluded.password_hash,
                        "locale": statement.excluded.locale,
                    },
                )
            )
        session.commit()
        return SeedUsersResult(valid_customer_ids, tuple(missing_customer_ids))


def build_manifest(customer_ids: tuple[str, ...]) -> list[dict[str, str]]:
    with create_session() as session:
        seeded_users = session.exec(
            select(User).where(User.customer_id.in_(customer_ids)).order_by(User.customer_id)
        ).all()
        return [
            {
                "user_id": user.id,
                "customer_id": user.customer_id,
                "email": user.email,
                "locale": user.locale,
            }
            for user in seeded_users
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
