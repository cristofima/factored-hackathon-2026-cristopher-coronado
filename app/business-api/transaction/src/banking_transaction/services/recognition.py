from __future__ import annotations

from datetime import timedelta
from typing import Any

from banking_shared.models import Product, TransactionRecord
from banking_shared.product_types import CARD_PRODUCT_TYPES
from sqlalchemy import func, or_
from sqlmodel import Session, select


def get_recognition_context(
    session: Session, transaction_id: str, customer_id: str,
) -> dict[str, Any]:
    selected = session.exec(
        select(TransactionRecord)
        .where(TransactionRecord.transaction_id == transaction_id)
        .where(TransactionRecord.customer_id == customer_id)
    ).first()
    product = None if selected is None else session.exec(
        select(Product)
        .where(Product.product_id == selected.product_id)
        .where(Product.customer_id == customer_id)
        .where(Product.product_type.in_(CARD_PRODUCT_TYPES))
    ).first()
    if selected is None or product is None:
        raise PermissionError("Transaction is unavailable for the authenticated customer")

    start = selected.transaction_date - timedelta(days=180)
    context: dict[str, Any] = {
        "transactionId": selected.transaction_id,
        "maskedCard": (
            f"**** {product.product_number[-4:]}"
            if product.product_number and len(product.product_number) > 4 else None
        ),
        "comparisonStart": start.isoformat(),
        "comparisonEndExclusive": selected.transaction_date.isoformat(),
        "lookbackDays": 180,
        "historyCoverage": "INSUFFICIENT_HISTORY",
        "coverageReason": "LOADED_WINDOW_UNVERIFIED",
        "queryComplete": True,
        "matches": [],
        "matchingRecordCount": 0,
        "matchesTruncated": False,
        "missingComparisonFieldCount": 0,
        "returnedFields": ["transactionId", "date", "merchant", "amount", "currency"],
        "persistedInSupportCase": False,
    }
    if (not selected.merchant_name or not selected.merchant_name.strip()
            or selected.transaction_type != "Purchase"
            or selected.transaction_status != "Approved"):
        context["coverageReason"] = "SELECTED_COMPARISON_FIELDS_UNAVAILABLE"
        return context

    window = (
        select(TransactionRecord)
        .where(TransactionRecord.customer_id == customer_id)
        .where(TransactionRecord.product_id == product.product_id)
        .where(TransactionRecord.transaction_id != transaction_id)
        .where(TransactionRecord.transaction_date >= start)
        .where(TransactionRecord.transaction_date < selected.transaction_date)
        .where(TransactionRecord.currency == selected.currency)
    )
    missing = window.where(or_(
        TransactionRecord.merchant_name.is_(None),
        func.trim(TransactionRecord.merchant_name) == "",
        TransactionRecord.transaction_type.is_(None),
        TransactionRecord.transaction_status.is_(None),
    ))
    context["missingComparisonFieldCount"] = session.exec(
        select(func.count()).select_from(missing.subquery())
    ).one()
    matching = window.where(
        TransactionRecord.transaction_type == "Purchase",
        TransactionRecord.transaction_status == "Approved",
        TransactionRecord.amount == selected.amount,
        func.lower(func.trim(TransactionRecord.merchant_name))
        == func.lower(func.trim(selected.merchant_name)),
    )
    context["matchingRecordCount"] = session.exec(
        select(func.count()).select_from(matching.subquery())
    ).one()
    records = session.exec(matching.order_by(
        TransactionRecord.transaction_date.desc(), TransactionRecord.transaction_id.desc(),
    ).limit(3)).all()
    context["matchesTruncated"] = context["matchingRecordCount"] > len(records)
    context["matches"] = [{
        "transactionId": record.transaction_id,
        "date": record.transaction_date.isoformat(),
        "merchant": record.merchant_name,
        "amount": str(record.amount),
        "currency": record.currency,
    } for record in records]
    return context
