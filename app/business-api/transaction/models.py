from pydantic import BaseModel, Field
from typing import Optional


class Transaction(BaseModel):
    id: str
    description: Optional[str] = None
    #deposits, withdrawals, transfers, and payments
    type: Optional[str] = None
    # income/outcome
    flowType: Optional[str] = None
    recipientName: Optional[str] = None
    recipientBankReference: Optional[str] = None
    product_number: Optional[str] = None
    #BankTransfer,DirectDebit,CreditCard
    paymentType: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    timestamp: Optional[str] = None
    category: Optional[str] = None
    #paid, pending, failed
    status: Optional[str] = None


class TransactionPage(BaseModel):
    items: list[Transaction]
    total: int
    limit: int
    offset: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None



class DisputeCase(BaseModel):
    caseId: str
    productNumber: Optional[str] = None
    transactionId: str
    reason: str
    status: str
    triageOutcome: Optional[str] = None
    resolutionOutcome: Optional[str] = None
    resolutionNotes: Optional[str] = None
    recommendationType: Optional[str] = None
    recommendationRationale: Optional[str] = None
    recommendationOptedOut: bool = False
    openedAt: str
    updatedAt: str
    resolvedAt: Optional[str] = None


class DisputeCaseEvent(BaseModel):
    eventType: str
    actor: str
    message: Optional[str] = None
    createdAt: str


class OpenDisputeRequest(BaseModel):
    transactionId: str
    reason: str


class DisputeApprovalRequest(BaseModel):
    approved: bool


class ResolveCaseRequest(BaseModel):
    resolutionOutcome: str
    resolutionNotes: Optional[str] = None

