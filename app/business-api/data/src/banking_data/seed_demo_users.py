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
from pathlib import Path

from identity.services import provisioning
from identity.services.provisioning import SeedUsersResult, locale_for_customer, password_hasher

from banking_data.database import create_session
from banking_data.resources import data_directory
from banking_data.shared import parse_customer_ids

DATA_DIR = data_directory()
DEMO_USER_PASSWORD_ENV = "DEMO_USER_PASSWORD"
ADMIN_BOOTSTRAP_PASSWORD_ENV = "ADMIN_BOOTSTRAP_PASSWORD"


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
    provisioning.validate_password(password, os.environ.get(ADMIN_BOOTSTRAP_PASSWORD_ENV))


def default_manifest_path(customer_ids: tuple[str, ...]) -> Path:
    artifacts_dir = Path(os.environ.get("DATA_ARTIFACTS_DIR", "").strip() or (DATA_DIR / "artifacts"))
    digest = hashlib.sha256(",".join(sorted(customer_ids)).encode("utf-8")).hexdigest()[:8]
    return artifacts_dir / f"demo_users_manifest_customers-{len(customer_ids)}-{digest}.json"


def seed_users(
    customer_ids: tuple[str, ...], locale: str | None, password: str
) -> SeedUsersResult:
    return provisioning.seed_users(
        customer_ids, locale, password, session_factory=create_session,
        administrator_password=os.environ.get(ADMIN_BOOTSTRAP_PASSWORD_ENV),
    )


def build_manifest(customer_ids: tuple[str, ...]) -> list[dict[str, str]]:
    return provisioning.build_manifest(customer_ids, session_factory=create_session)


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
