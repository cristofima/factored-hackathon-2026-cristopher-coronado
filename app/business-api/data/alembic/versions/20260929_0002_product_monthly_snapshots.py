"""Create derived monthly product balance snapshots.

Revision ID: 20260929_0002
Revises: 20260928_0001
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260929_0002"
down_revision: str | None = "20260928_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_monthly_snapshots",
        sa.Column(
            "product_id",
            sa.String(64),
            sa.ForeignKey("products.product_id"),
            primary_key=True,
        ),
        sa.Column("snapshot_month", sa.Date(), primary_key=True),
        sa.Column("closing_balance", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("approved_transaction_count", sa.Integer(), nullable=False),
        sa.Column("net_transaction_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("excluded_approved_transaction_count", sa.Integer(), nullable=False),
        sa.Column("excluded_approved_transaction_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("balance_uncertainty_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("anchor_balance", sa.Numeric(20, 4), nullable=False),
        sa.Column("anchor_date", sa.Date(), nullable=False),
        sa.Column("calculation_method", sa.String(64), nullable=False),
        sa.Column("transaction_policy", sa.String(512), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_product_monthly_snapshots_month",
        "product_monthly_snapshots",
        ["snapshot_month"],
    )


def downgrade() -> None:
    op.drop_table("product_monthly_snapshots")