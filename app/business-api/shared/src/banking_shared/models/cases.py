from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Column, DateTime, Index, Integer, JSON, Numeric, column
from sqlmodel import Field, SQLModel

CUSTOMER_ID_FOREIGN_KEY = "customers.customer_id"
PRODUCT_ID_FOREIGN_KEY = "products.product_id"
TRANSACTION_ID_FOREIGN_KEY = "transactions.transaction_id"


SUPPORT_CASE_STATUSES = (
    "OPEN", "WAITING_USER_APPROVAL", "IN_REVIEW", "PENDING_EFFECTS",
    "RESOLVED_VALID", "RESOLVED_INVALID", "RESOLVED",
)


class SupportCase(SQLModel, table=True):
    __tablename__ = "support_cases"
    __table_args__ = (
        Index("ix_support_cases_customer_status", "customer_id", "status"),
        Index("ix_support_cases_transaction", "transaction_id"),
        Index("uq_support_cases_active_transaction", "transaction_id", unique=True,
              postgresql_where=column("status").in_(("OPEN", "WAITING_USER_APPROVAL", "IN_REVIEW", "PENDING_EFFECTS")),
              sqlite_where=column("status").in_(("OPEN", "WAITING_USER_APPROVAL", "IN_REVIEW", "PENDING_EFFECTS"))),
        Index("ix_support_cases_operator_queue", "status", "assigned_operator_sub", "opened_at"),
        {"schema": "support"},
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
    legacy_assigned_agent_id: str | None = Field(default=None, max_length=64)
    assigned_operator_sub: str | None = Field(
        default=None, foreign_key="operators.user_id", ondelete="RESTRICT", max_length=36,
    )
    claimed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    claim_version: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    case_version: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    evidence_version: int = Field(default=0, sa_column=Column(Integer, nullable=False, server_default="0"))
    evidence_snapshot: dict | None = Field(default=None, sa_column=Column(JSON))
    verdict: str | None = Field(default=None, max_length=16)
    effect_code: str | None = Field(default=None, max_length=64)
    resolution_outcome: str | None = Field(default=None, max_length=64)
    resolution_notes: str | None = Field(default=None, max_length=1000)
    recommendation_type: str | None = Field(default=None, max_length=64)
    recommendation_rationale: str | None = Field(default=None, max_length=500)
    recommendation_opted_out: bool = Field(default=False)
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
    __table_args__ = (
        Index("ix_support_case_events_case_created", "case_id", "created_at"),
        {"schema": "support"},
    )

    event_id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, max_length=36)
    case_id: str = Field(foreign_key="support.support_cases.case_id", index=True, max_length=64)
    event_type: str = Field(max_length=64)
    actor: str = Field(max_length=32)
    message: str | None = Field(default=None, max_length=1000)
    operator_sub: str | None = Field(default=None, max_length=36)
    operator_identity_version: int | None = Field(default=None)
    claim_version: int | None = Field(default=None)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
