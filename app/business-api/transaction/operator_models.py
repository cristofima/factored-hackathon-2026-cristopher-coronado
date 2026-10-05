"""Operator queue, versioned adjudication and recorded-effect contracts."""
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class AdjudicateRequest(BaseModel):
    verdict: Literal["valid", "invalid"]
    rationale: str = Field(min_length=1, max_length=1000)
    expected_case_version: int = Field(ge=0)
    expected_evidence_version: int = Field(ge=1)
    destination_product_id: str | None = None

    @field_validator("rationale")
    @classmethod
    def nonblank_rationale(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Rationale is required")
        return value.strip()


class RetryEffectsRequest(BaseModel):
    expected_case_version: int = Field(ge=0)
    destination_product_id: str | None = None


class CardProtectionRequest(BaseModel):
    expected_case_version: int = Field(ge=0)
    rationale: str = Field(min_length=1, max_length=1000)
    blocked: bool

    @field_validator("rationale")
    @classmethod
    def nonblank_rationale(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Rationale is required")
        return value.strip()


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
    caseVersion: int = 0
    evidenceVersion: int = 0
    evidence: dict[str, object] | None = None
    verdict: str | None = None
    rationale: str | None = None
    eligibleDestinations: list[dict[str, str | None]] = Field(default_factory=list)
    effects: dict[str, str] | None = None
    effectCode: str | None = None
    cardProtection: dict[str, object] | None = None
    productProtectionStatus: str | None = None
