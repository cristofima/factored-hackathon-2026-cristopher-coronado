from __future__ import annotations

from datetime import date
from typing import Literal

from sqlalchemy import CheckConstraint, Column, Index, String
from sqlmodel import Field, SQLModel

BRANCH_ID_FOREIGN_KEY = "branches.branch_id"


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
    __table_args__ = (
        CheckConstraint(
            "customer_status IN ('Active', 'Inactive', 'Suspended', 'Closed')",
            name="ck_customers_status",
        ),
        CheckConstraint("length(email) <= 120", name="ck_customers_email_length"),
        CheckConstraint("length(first_name) <= 50", name="ck_customers_first_name_length"),
        CheckConstraint("length(last_name) <= 50", name="ck_customers_last_name_length"),
        CheckConstraint("length(country) <= 100", name="ck_customers_country_length"),
        Index("ix_customers_first_name", "first_name"),
        Index("ix_customers_last_name", "last_name"),
        Index("ix_customers_country", "country"),
        Index("ix_customers_customer_status", "customer_status"),
    )

    customer_id: str = Field(primary_key=True, max_length=64)
    email: str = Field(index=True, max_length=120)
    first_name: str | None = Field(default=None, max_length=50)
    last_name: str | None = Field(default=None, max_length=50)
    country: str | None = Field(default=None, max_length=100)
    detected_accent: str | None = Field(default=None, max_length=32)
    segment: str | None = Field(default=None, max_length=64)
    registration_date: date | None = None
    registration_branch_id: str | None = Field(
        default=None,
        foreign_key=BRANCH_ID_FOREIGN_KEY,
        max_length=64,
    )
    customer_status: Literal["Active", "Inactive", "Suspended", "Closed"] | None = Field(
        default=None, sa_column=Column(String(64), nullable=True),
    )
