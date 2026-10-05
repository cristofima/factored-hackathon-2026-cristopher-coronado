"""Versioned adjudication, unique entitlement and ingestion-independent effects."""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0011"
down_revision = "20261004_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    active = ("OPEN", "WAITING_USER_APPROVAL", "IN_REVIEW", "PENDING_EFFECTS")
    connection = op.get_bind()
    cases = sa.Table("support_cases", sa.MetaData(), autoload_with=connection)
    duplicates = connection.execute(sa.select(cases.c.transaction_id).where(
        cases.c.status.in_(active)
    ).group_by(cases.c.transaction_id).having(sa.func.count() > 1).limit(1)).first()
    if duplicates is not None:
        raise RuntimeError("Duplicate active disputes require explicit reconciliation before migration")
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("source_kind", sa.String(16), nullable=False, server_default="source"))
        batch.add_column(sa.Column("original_transaction_id", sa.String(64)))
        batch.add_column(sa.Column("support_case_id", sa.String(64)))
    with op.batch_alter_table("support_cases") as batch:
        batch.add_column(sa.Column("case_version", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("evidence_version", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("evidence_snapshot", sa.JSON()))
        batch.add_column(sa.Column("verdict", sa.String(16)))
        batch.add_column(sa.Column("effect_code", sa.String(64)))
    predicate = sa.column("status").in_(active)
    op.create_index("uq_support_cases_active_transaction", "support_cases", ["transaction_id"],
                    unique=True, postgresql_where=predicate, sqlite_where=predicate)
    op.create_table("runtime_postings",
        sa.Column("original_transaction_id", sa.String(64), sa.ForeignKey("transactions.transaction_id"), primary_key=True),
        sa.Column("case_id", sa.String(64), sa.ForeignKey("support_cases.case_id"), nullable=False, unique=True),
        sa.Column("movement_id", sa.String(64), sa.ForeignKey("transactions.transaction_id"), nullable=False, unique=True),
        sa.Column("product_id", sa.String(64), sa.ForeignKey("products.product_id"), nullable=False),
        sa.Column("customer_id", sa.String(64), sa.ForeignKey("customers.customer_id"), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("balance_delta", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("operator_sub", sa.String(36), sa.ForeignKey("operators.user_id"), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_runtime_postings_product_id", "runtime_postings", ["product_id"])
    op.create_table("card_protections",
        sa.Column("product_id", sa.String(64), sa.ForeignKey("products.product_id"), primary_key=True),
        sa.Column("case_id", sa.String(64), sa.ForeignKey("support_cases.case_id"), nullable=False),
        sa.Column("prior_status", sa.String(32)),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("rationale", sa.String(1000), nullable=False),
        sa.Column("operator_sub", sa.String(36), sa.ForeignKey("operators.user_id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    raise RuntimeError("Financial entitlement and original effect audit must not be discarded")
