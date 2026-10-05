from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, DateTime, Index, Numeric
from sqlmodel import Field, SQLModel

CUSTOMER_ID_FOREIGN_KEY = "customers.customer_id"
PRODUCT_ID_FOREIGN_KEY = "products.product_id"


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
