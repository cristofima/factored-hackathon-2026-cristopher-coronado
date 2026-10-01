from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, Numeric, UniqueConstraint
from sqlmodel import Field, SQLModel

BRANCH_ID_FOREIGN_KEY = "branches.branch_id"
CUSTOMER_ID_FOREIGN_KEY = "customers.customer_id"
PRODUCT_ID_FOREIGN_KEY = "products.product_id"
TRANSACTION_ID_FOREIGN_KEY = "transactions.transaction_id"


class Branch(SQLModel, table=True):
    __tablename__ = "branches"

    branch_id: str = Field(primary_key=True, max_length=64)
    branch_code: str | None = Field(default=None, max_length=64)
    branch_name: str | None = Field(default=None, max_length=200)
    branch_type: str | None = Field(default=None, max_length=64)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    branch_status: str | None = Field(default=None, max_length=64)


class Customer(SQLModel, table=True):
    __tablename__ = "customers"

    customer_id: str = Field(primary_key=True, max_length=64)
    email: str = Field(index=True, max_length=320)
    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    detected_accent: str | None = Field(default=None, max_length=32)
    segment: str | None = Field(default=None, max_length=64)
    registration_date: date | None = None
    registration_branch_id: str | None = Field(
        default=None,
        foreign_key=BRANCH_ID_FOREIGN_KEY,
        max_length=64,
    )
    customer_status: str | None = Field(default=None, max_length=64)


class ServiceAgent(SQLModel, table=True):
    __tablename__ = "service_agents"

    agent_id: str = Field(primary_key=True, max_length=64)
    employee_code: str | None = Field(default=None, max_length=64)
    assigned_branch_id: str | None = Field(
        default=None,
        foreign_key=BRANCH_ID_FOREIGN_KEY,
        max_length=64,
    )
    agent_type: str | None = Field(default=None, max_length=64)
    experience_level: str | None = Field(default=None, max_length=64)
    languages: str | None = Field(default=None, max_length=250)
    specialty: str | None = Field(default=None, max_length=120)
    agent_status: str | None = Field(default=None, max_length=64)


class Product(SQLModel, table=True):
    __tablename__ = "products"
    __table_args__ = (Index("ix_products_customer_type", "customer_id", "product_type"),)

    product_id: str = Field(primary_key=True, max_length=64)
    customer_id: str = Field(
        foreign_key=CUSTOMER_ID_FOREIGN_KEY,
        index=True,
        max_length=64,
    )
    product_type: str = Field(index=True, max_length=64)
    product_number: str | None = Field(default=None, max_length=120)
    currency: str = Field(max_length=8)
    current_balance: Decimal | None = Field(default=None, sa_column=Column(Numeric(20, 4)))
    credit_limit: Decimal | None = Field(default=None, sa_column=Column(Numeric(20, 4)))
    interest_rate: Decimal | None = Field(default=None, sa_column=Column(Numeric(12, 6)))
    opening_date: date | None = None
    expiration_date: date | None = None
    product_status: str | None = Field(default=None, max_length=64)
    last_transaction_date: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True)),
    )


class ProductMonthlySnapshot(SQLModel, table=True):
    __tablename__ = "product_monthly_snapshots"
    __table_args__ = (Index("ix_product_monthly_snapshots_month", "snapshot_month"),)

    product_id: str = Field(primary_key=True, foreign_key=PRODUCT_ID_FOREIGN_KEY, max_length=64)
    snapshot_month: date = Field(primary_key=True)
    closing_balance: Decimal = Field(sa_column=Column(Numeric(20, 4), nullable=False))
    currency: str = Field(max_length=8)
    approved_transaction_count: int
    net_transaction_amount: Decimal = Field(sa_column=Column(Numeric(20, 4), nullable=False))
    excluded_approved_transaction_count: int
    excluded_approved_transaction_amount: Decimal = Field(
        sa_column=Column(Numeric(20, 4), nullable=False)
    )
    balance_uncertainty_amount: Decimal = Field(
        sa_column=Column(Numeric(20, 4), nullable=False)
    )
    anchor_balance: Decimal = Field(sa_column=Column(Numeric(20, 4), nullable=False))
    anchor_date: date
    calculation_method: str = Field(max_length=64)
    transaction_policy: str = Field(max_length=512)
    calculated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class TransactionRecord(SQLModel, table=True):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_product_date", "product_id", "transaction_date"),
        Index("ix_transactions_customer_date", "customer_id", "transaction_date"),
    )

    transaction_id: str = Field(primary_key=True, max_length=64)
    transaction_date: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    process_date: date = Field(index=True)
    product_id: str = Field(foreign_key=PRODUCT_ID_FOREIGN_KEY, max_length=64)
    customer_id: str = Field(foreign_key=CUSTOMER_ID_FOREIGN_KEY, max_length=64)
    transaction_type: str | None = Field(default=None, max_length=64)
    transaction_category: str | None = Field(default=None, max_length=120)
    amount: Decimal = Field(sa_column=Column(Numeric(20, 4), nullable=False))
    currency: str = Field(max_length=8)
    amount_usd: Decimal | None = Field(default=None, sa_column=Column(Numeric(20, 4)))
    channel: str | None = Field(default=None, max_length=64)
    branch_id: str | None = Field(
        default=None,
        foreign_key=BRANCH_ID_FOREIGN_KEY,
        max_length=64,
    )
    merchant_name: str | None = Field(default=None, max_length=250)
    merchant_category: str | None = Field(default=None, max_length=120)
    transaction_country: str | None = Field(default=None, max_length=120)
    transaction_city: str | None = Field(default=None, max_length=120)
    transaction_status: str | None = Field(default=None, max_length=64)
    response_code: str | None = Field(default=None, max_length=32)
    is_fraud: bool | None = Field(default=None)
    fraud_score: Decimal | None = Field(default=None, sa_column=Column(Numeric(6, 4)))


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("customer_id", name="uq_users_customer_id"),)

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, max_length=36)
    customer_id: str = Field(foreign_key=CUSTOMER_ID_FOREIGN_KEY, max_length=64)
    email: str = Field(unique=True, index=True, max_length=320)
    password_hash: str = Field(max_length=500)
    locale: str = Field(max_length=8)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


# Valid support_cases.status values, in required transition order.
SUPPORT_CASE_STATUSES = ("OPEN", "WAITING_USER_APPROVAL", "IN_REVIEW", "RESOLVED")


class SupportCase(SQLModel, table=True):
    __tablename__ = "support_cases"
    __table_args__ = (
        Index("ix_support_cases_customer_status", "customer_id", "status"),
        Index("ix_support_cases_transaction", "transaction_id"),
    )

    case_id: str = Field(
        default_factory=lambda: f"CASE-{uuid4().hex[:20].upper()}",
        primary_key=True,
        max_length=64,
    )
    customer_id: str = Field(foreign_key=CUSTOMER_ID_FOREIGN_KEY, index=True, max_length=64)
    product_id: str = Field(foreign_key=PRODUCT_ID_FOREIGN_KEY, max_length=64)
    transaction_id: str = Field(foreign_key=TRANSACTION_ID_FOREIGN_KEY, max_length=64)
    case_type: str = Field(default="transaction_dispute", max_length=64)
    reason: str = Field(max_length=1000)
    status: str = Field(default="OPEN", max_length=32)
    fraud_score_at_open: Decimal | None = Field(default=None, sa_column=Column(Numeric(6, 4)))
    triage_outcome: str | None = Field(default=None, max_length=32)
    assigned_agent_id: str | None = Field(
        default=None,
        foreign_key="service_agents.agent_id",
        max_length=64,
    )
    resolution_outcome: str | None = Field(default=None, max_length=64)
    resolution_notes: str | None = Field(default=None, max_length=1000)
    opened_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    resolved_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class SupportCaseEvent(SQLModel, table=True):
    __tablename__ = "support_case_events"
    __table_args__ = (Index("ix_support_case_events_case_created", "case_id", "created_at"),)

    event_id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, max_length=36)
    case_id: str = Field(foreign_key="support_cases.case_id", index=True, max_length=64)
    event_type: str = Field(max_length=64)
    actor: str = Field(max_length=32)
    message: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
