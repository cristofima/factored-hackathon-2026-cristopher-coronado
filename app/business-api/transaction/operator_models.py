"""Minimal operator queue and exclusive takeover response contracts."""
from pydantic import BaseModel


class OperatorCaseSummary(BaseModel):
    caseId: str
    status: str
    openedAt: str
    updatedAt: str
    triageOutcome: str | None
    claimVersion: int


class OperatorCasePage(BaseModel):
    items: list[OperatorCaseSummary]
    total: int
    offset: int
    limit: int


class OperatorCaseEvent(BaseModel):
    eventId: str
    eventType: str
    actor: str
    message: str | None
    createdAt: str
    operatorSub: str | None
    operatorIdentityVersion: int | None
    claimVersion: int | None


class OperatorCaseDetail(OperatorCaseSummary):
    assignedOperatorSub: str
    claimedAt: str
    reason: str
    transactionId: str
    productId: str
    events: list[OperatorCaseEvent]
