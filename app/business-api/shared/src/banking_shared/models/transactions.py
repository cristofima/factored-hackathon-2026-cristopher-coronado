from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Column, DateTime, Index, Numeric, String
from sqlmodel import Field, SQLModel

BRANCH_ID_FOREIGN_KEY = "branches.branch_id"
CUSTOMER_ID_FOREIGN_KEY = "customers.customer_id"
PRODUCT_ID_FOREIGN_KEY = "products.product_id"


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
    source_kind: str = Field(default="source", sa_column=Column(String(16), nullable=False, server_default="source"))
    original_transaction_id: str | None = Field(default=None, max_length=64)
    support_case_id: str | None = Field(default=None, max_length=64)
