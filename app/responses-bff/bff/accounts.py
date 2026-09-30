"""Authenticated, customer-scoped account transaction reads."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from bff.auth import AuthenticatedUser, get_authenticated_user
from bff.user_repository import UserRepository


class TransactionSummary(BaseModel):
    id: str
    account_id: str
    date: datetime
    amount: str
    currency: str
    type: str | None
    category: str | None
    channel: str | None
    merchant: str | None
    status: str | None


class TransactionPage(BaseModel):
    items: list[TransactionSummary]
    total: int
    limit: int
    offset: int
    start_date: date | None
    end_date: date | None


router = APIRouter(prefix="/accounts")


@router.get("/{account_id}/transactions", response_model=TransactionPage)
def get_account_transactions(
    account_id: str,
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
    start_date: date | None = None,
    end_date: date | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionPage:
    """Read an owned bank account's transactions with inclusive calendar dates."""
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not exceed end_date")
    repository: UserRepository = request.app.state.user_repository
    try:
        result = repository.list_transactions(
            user.sub, user.customer_id, account_id, start_date, end_date, limit, offset,
        )
    except (RuntimeError, SQLAlchemyError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Transactions are temporarily unavailable",
        ) from None
    if result is None:
        raise HTTPException(status_code=404, detail="Account not found")
    records, total = result
    return TransactionPage(
        items=[TransactionSummary(
            id=record.transaction_id, account_id=record.product_id,
            date=record.transaction_date, amount=format(record.amount, "f"),
            currency=record.currency, type=record.transaction_type,
            category=record.transaction_category, channel=record.channel,
            merchant=record.merchant_name, status=record.transaction_status,
        ) for record in records],
        total=total, limit=limit, offset=offset, start_date=start_date, end_date=end_date,
    )