"""Consolidate support tables and add bounded customer-provided conversation evidence."""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0012"
down_revision = "20261004_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.schema.CreateSchema("support"))
    for table_name in (
        "support_cases", "support_case_events", "runtime_postings", "card_protections",
    ):
        op.execute(sa.DDL(f'ALTER TABLE public."{table_name}" SET SCHEMA support'))
    op.create_table(
        "case_conversations",
        sa.Column("case_id", sa.String(64), primary_key=True),
        sa.Column("messages", sa.JSON(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["case_id"], ["support.support_cases.case_id"], ondelete="RESTRICT"),
        schema="support",
    )


def downgrade() -> None:
    raise RuntimeError("Customer-provided case evidence requires explicit retention review before removal")
