"""Create the banking ownership schema.

Revision ID: 20260928_0001
Revises:
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260928_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BRANCH_ID_FOREIGN_KEY = "branches.branch_id"
CUSTOMER_ID_FOREIGN_KEY = "customers.customer_id"


def upgrade() -> None:
    op.create_table(
        "branches",
        sa.Column("branch_id", sa.String(64), primary_key=True),
        sa.Column("branch_code", sa.String(64)),
        sa.Column("branch_name", sa.String(200)),
        sa.Column("branch_type", sa.String(64)),
        sa.Column("city", sa.String(120)),
        sa.Column("state", sa.String(120)),
        sa.Column("country", sa.String(120)),
        sa.Column("branch_status", sa.String(64)),
    )
    op.create_table(
        "customers",
        sa.Column("customer_id", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("first_name", sa.String(120)),
        sa.Column("last_name", sa.String(120)),
        sa.Column("country", sa.String(120)),
        sa.Column("detected_accent", sa.String(32)),
        sa.Column("segment", sa.String(64)),
        sa.Column("registration_date", sa.Date()),
        sa.Column("registration_branch_id", sa.String(64), sa.ForeignKey(BRANCH_ID_FOREIGN_KEY)),
        sa.Column("customer_status", sa.String(64)),
    )
    op.create_index("ix_customers_email", "customers", ["email"])
    op.create_table(
        "service_agents",
        sa.Column("agent_id", sa.String(64), primary_key=True),
        sa.Column("employee_code", sa.String(64)),
        sa.Column("assigned_branch_id", sa.String(64), sa.ForeignKey(BRANCH_ID_FOREIGN_KEY)),
        sa.Column("agent_type", sa.String(64)),
        sa.Column("experience_level", sa.String(64)),
        sa.Column("languages", sa.String(250)),
        sa.Column("specialty", sa.String(120)),
        sa.Column("agent_status", sa.String(64)),
    )
    op.create_table(
        "products",
        sa.Column("product_id", sa.String(64), primary_key=True),
        sa.Column("customer_id", sa.String(64), sa.ForeignKey(CUSTOMER_ID_FOREIGN_KEY), nullable=False),
        sa.Column("product_type", sa.String(64), nullable=False),
        sa.Column("product_number", sa.String(120)),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("current_balance", sa.Numeric(20, 4)),
        sa.Column("credit_limit", sa.Numeric(20, 4)),
        sa.Column("interest_rate", sa.Numeric(12, 6)),
        sa.Column("opening_date", sa.Date()),
        sa.Column("expiration_date", sa.Date()),
        sa.Column("product_status", sa.String(64)),
        sa.Column("last_transaction_date", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_products_customer_id", "products", ["customer_id"])
    op.create_index("ix_products_product_type", "products", ["product_type"])
    op.create_index("ix_products_customer_type", "products", ["customer_id", "product_type"])
    op.create_table(
        "transactions",
        sa.Column("transaction_id", sa.String(64), primary_key=True),
        sa.Column("transaction_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("process_date", sa.Date(), nullable=False),
        sa.Column("product_id", sa.String(64), sa.ForeignKey("products.product_id"), nullable=False),
        sa.Column("customer_id", sa.String(64), sa.ForeignKey(CUSTOMER_ID_FOREIGN_KEY), nullable=False),
        sa.Column("transaction_type", sa.String(64)),
        sa.Column("transaction_category", sa.String(120)),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("channel", sa.String(64)),
        sa.Column("branch_id", sa.String(64), sa.ForeignKey(BRANCH_ID_FOREIGN_KEY)),
        sa.Column("merchant_name", sa.String(250)),
        sa.Column("merchant_category", sa.String(120)),
        sa.Column("transaction_status", sa.String(64)),
    )
    op.create_index("ix_transactions_process_date", "transactions", ["process_date"])
    op.create_index("ix_transactions_product_date", "transactions", ["product_id", "transaction_date"])
    op.create_index("ix_transactions_customer_date", "transactions", ["customer_id", "transaction_date"])
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("customer_id", sa.String(64), sa.ForeignKey(CUSTOMER_ID_FOREIGN_KEY), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(500), nullable=False),
        sa.Column("locale", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("customer_id", name="uq_users_customer_id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_table("users")
    op.drop_table("transactions")
    op.drop_table("products")
    op.drop_table("service_agents")
    op.drop_table("customers")
    op.drop_table("branches")