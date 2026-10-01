from typing import List, Optional
from pydantic import BaseModel, Field


class PaymentMethodSummary(BaseModel):
    number: Optional[str] = None
    type: str
    name: Optional[str] = None
    activationDate: Optional[str] = None
    expirationDate: Optional[str] = None


class PaymentMethod(BaseModel):
    type: str
    activationDate: Optional[str] = None
    expirationDate: Optional[str] = None
    availableBalance: Optional[float] = None
    cardNumber: Optional[str] = None
    #blocked,active, expired
    status: Optional[str] = None


class Card(BaseModel):
    #credit,debit,recharge
    type: str
    #Visa, Master Card, Amex, Diners Club, Discover
    circuit: Optional[str] = None
    name: str
    activationDate: Optional[str] = None
    expirationDate: Optional[str] = None
    balance: Optional[float] = None
    rechargedAmount: Optional[float] = None
    number: Optional[str] = None
    limit: Optional[float] = None
    #blocked,active, expired
    status: Optional[str] = None
    cvv: Optional[str] = None


class Beneficiary(BaseModel):
    id: str
    fullName: str
    bankCode: str
    bankName: str


class Account(BaseModel):
    accountNumber: Optional[str] = Field(
        default=None,
        description="Persisted bank account product number; never the internal product id",
    )
    userName: str
    accountHolderFullName: str
    currency: str
    activationDate: Optional[str] = None
    balance: Optional[str] = None
    paymentMethods: Optional[List[PaymentMethodSummary]] = None


class AccountSummary(BaseModel):
    type: str
    status: Optional[str] = None
    opened: Optional[str] = None
    number: Optional[str] = None
    currency: str
    balance: Optional[str] = None


class CardSummary(AccountSummary):
    expires: Optional[str] = None
    credit_limit: Optional[str] = None

