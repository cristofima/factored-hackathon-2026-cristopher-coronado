"""Allow audited customer sign-in lifecycle changes without rewriting history."""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20261003_0008"
down_revision: str | None = "20261003_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("identity_audits") as batch:
        batch.drop_constraint("ck_identity_audits_action", type_="check")
        batch.create_check_constraint(
            "ck_identity_audits_action",
            "action IN ('login', 'operator_create', 'operator_activate', "
            "'operator_deactivate', 'operator_reset_password', 'admin_bootstrap', "
            "'customer_migrate', 'customer_activate', 'customer_deactivate')",
        )


def downgrade() -> None:
    raise RuntimeError("Customer lifecycle audit migration is forward-only; preserve identity history")
