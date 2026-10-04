"""Add real operator takeover without altering catalog assignment or history."""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261004_0009"
down_revision: str | None = "20261003_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("support_cases", sa.Column("assigned_operator_sub", sa.String(36)))
    op.add_column("support_cases", sa.Column("claimed_at", sa.DateTime(timezone=True)))
    op.add_column("support_cases", sa.Column("claim_version", sa.Integer(), nullable=False,
                                           server_default="0"))
    op.create_index("ix_support_cases_operator_queue", "support_cases",
                    ["status", "assigned_operator_sub", "opened_at"])
    op.add_column("support_case_events", sa.Column("operator_sub", sa.String(36)))
    op.add_column("support_case_events", sa.Column("operator_identity_version", sa.Integer()))
    op.add_column("support_case_events", sa.Column("claim_version", sa.Integer()))


def downgrade() -> None:
    raise RuntimeError("Operator takeover migration is forward-only; preserve assignment audit history")
