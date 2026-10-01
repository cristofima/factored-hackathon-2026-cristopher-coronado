"""Add the post-resolution recommendation columns to support_cases.

Revision ID: 20261001_0005
Revises: 20261001_0004
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261001_0005"
down_revision: str | None = "20261001_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "support_cases", sa.Column("recommendation_type", sa.String(64), nullable=True)
    )
    op.add_column(
        "support_cases", sa.Column("recommendation_rationale", sa.String(500), nullable=True)
    )
    op.add_column(
        "support_cases",
        sa.Column(
            "recommendation_opted_out",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("support_cases", "recommendation_opted_out")
    op.drop_column("support_cases", "recommendation_rationale")
    op.drop_column("support_cases", "recommendation_type")
