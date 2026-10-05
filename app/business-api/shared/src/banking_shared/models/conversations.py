"""Append-once customer-provided case evidence, not provider execution records."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, JSON
from sqlmodel import Field, SQLModel


class CaseConversationSnapshot(SQLModel, table=True):
    __tablename__ = "case_conversations"
    __table_args__ = {"schema": "support"}

    case_id: str = Field(
        primary_key=True,
        foreign_key="support.support_cases.case_id",
        ondelete="RESTRICT",
        max_length=64,
    )
    messages: list[dict[str, str]] = Field(sa_column=Column(JSON, nullable=False))
    captured_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
