from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, DateTime, Numeric
from sqlmodel import Field, SQLModel

CUSTOMER_ID_FOREIGN_KEY = "customers.customer_id"
PRODUCT_ID_FOREIGN_KEY = "products.product_id"
TRANSACTION_ID_FOREIGN_KEY = "transactions.transaction_id"


class RuntimePosting(SQLModel, table=True):
    __tablename__ = "runtime_postings"

    original_transaction_id: str = Field(primary_key=True, foreign_key=TRANSACTION_ID_FOREIGN_KEY, max_length=64)
    case_id: str = Field(foreign_key="support_cases.case_id", unique=True, max_length=64)
    movement_id: str = Field(foreign_key=TRANSACTION_ID_FOREIGN_KEY, unique=True, max_length=64)
    product_id: str = Field(foreign_key=PRODUCT_ID_FOREIGN_KEY, index=True, max_length=64)
    customer_id: str = Field(foreign_key=CUSTOMER_ID_FOREIGN_KEY, max_length=64)
    amount: Decimal = Field(sa_column=Column(Numeric(20, 4), nullable=False))
    balance_delta: Decimal = Field(sa_column=Column(Numeric(20, 4), nullable=False))
    currency: str = Field(max_length=8)
    operator_sub: str = Field(foreign_key="operators.user_id", max_length=36)
    executed_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class CardProtection(SQLModel, table=True):
    __tablename__ = "card_protections"

    product_id: str = Field(primary_key=True, foreign_key=PRODUCT_ID_FOREIGN_KEY, max_length=64)
    case_id: str = Field(foreign_key="support_cases.case_id", max_length=64)
    prior_status: str | None = Field(default=None, max_length=32)
    blocked: bool = Field(default=True)
    rationale: str = Field(max_length=1000)
    operator_sub: str = Field(foreign_key="operators.user_id", max_length=36)
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
