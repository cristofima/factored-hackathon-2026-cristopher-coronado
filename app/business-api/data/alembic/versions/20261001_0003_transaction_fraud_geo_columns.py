"""Widen transactions with persisted geo, response, and fraud-signal columns.

Revision ID: 20261001_0003
Revises: 20260929_0002
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261001_0003"
down_revision: str | None = "20260929_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("amount_usd", sa.Numeric(20, 4), nullable=True))
    op.add_column("transactions", sa.Column("transaction_country", sa.String(120), nullable=True))
    op.add_column("transactions", sa.Column("transaction_city", sa.String(120), nullable=True))
    op.add_column("transactions", sa.Column("response_code", sa.String(32), nullable=True))
    op.add_column("transactions", sa.Column("is_fraud", sa.Boolean(), nullable=True))
    op.add_column("transactions", sa.Column("fraud_score", sa.Numeric(6, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("transactions", "fraud_score")
    op.drop_column("transactions", "is_fraud")
    op.drop_column("transactions", "response_code")
    op.drop_column("transactions", "transaction_city")
    op.drop_column("transactions", "transaction_country")
    op.drop_column("transactions", "amount_usd")
