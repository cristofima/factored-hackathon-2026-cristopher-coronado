"""Create the persisted support-case workflow tables.

Revision ID: 20261001_0004
Revises: 20261001_0003
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261001_0004"
down_revision: str | None = "20261001_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_cases",
        sa.Column("case_id", sa.String(64), primary_key=True),
        sa.Column(
            "customer_id",
            sa.String(64),
            sa.ForeignKey("customers.customer_id"),
            nullable=False,
        ),
        sa.Column(
            "product_id", sa.String(64), sa.ForeignKey("products.product_id"), nullable=False
        ),
        sa.Column(
            "transaction_id",
            sa.String(64),
            sa.ForeignKey("transactions.transaction_id"),
            nullable=False,
        ),
        sa.Column("case_type", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("fraud_score_at_open", sa.Numeric(6, 4), nullable=True),
        sa.Column("triage_outcome", sa.String(32), nullable=True),
        sa.Column(
            "assigned_agent_id",
            sa.String(64),
            sa.ForeignKey("service_agents.agent_id"),
            nullable=True,
        ),
        sa.Column("resolution_outcome", sa.String(64), nullable=True),
        sa.Column("resolution_notes", sa.String(1000), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_support_cases_customer_status", "support_cases", ["customer_id", "status"]
    )
    op.create_index("ix_support_cases_transaction", "support_cases", ["transaction_id"])

    op.create_table(
        "support_case_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column(
            "case_id", sa.String(64), sa.ForeignKey("support_cases.case_id"), nullable=False
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(32), nullable=False),
        sa.Column("message", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_support_case_events_case_created",
        "support_case_events",
        ["case_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("support_case_events")
    op.drop_table("support_cases")
