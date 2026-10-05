"""Fetch persisted snapshot inputs and project calculated values."""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, case, cast, func
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, select
from sqlmodel.sql.expression import SelectOfScalar

from banking_data.models import Product, TransactionRecord
from banking_data.snapshots.snapshot_calculations import (
    CALCULATION_METHOD,
    INCLUDED_STATUS,
    MonthlyMovement,
    TransactionPolicy,
    build_snapshot_values,
)


def _selected_products_statement(customer_ids: tuple[str, ...]) -> SelectOfScalar[Product]:
    statement = select(Product)
    if customer_ids:
        statement = statement.where(Product.customer_id.in_(customer_ids))
    return statement.order_by(Product.product_id)


def _selected_transactions_filter(customer_ids: tuple[str, ...]) -> ColumnElement[bool] | None:
    if customer_ids:
        return TransactionRecord.customer_id.in_(customer_ids)
    return None


def load_coverage(session: Session, customer_ids: tuple[str, ...]) -> tuple[date, date]:
    statement = select(
        func.min(TransactionRecord.process_date),
        func.max(TransactionRecord.process_date),
    )
    transaction_filter = _selected_transactions_filter(customer_ids)
    if transaction_filter is not None:
        statement = statement.where(transaction_filter)
    minimum_date, maximum_date = session.exec(statement).one()
    if minimum_date is None or maximum_date is None:
        raise ValueError("No transactions exist for the selected customers")
    return minimum_date, maximum_date


def load_observed_types(session: Session, customer_ids: tuple[str, ...]) -> set[str]:
    statement = (
        select(TransactionRecord.transaction_type)
        .where(TransactionRecord.source_kind == "source")
        .where(TransactionRecord.transaction_status == INCLUDED_STATUS)
        .distinct()
    )
    transaction_filter = _selected_transactions_filter(customer_ids)
    if transaction_filter is not None:
        statement = statement.where(transaction_filter)
    values = session.exec(statement).all()
    if any(value is None for value in values):
        raise ValueError("Approved transactions contain a null transaction type")
    return {value for value in values if value is not None}


def load_movements(
    session: Session,
    customer_ids: tuple[str, ...],
    policy: TransactionPolicy,
) -> dict[str, dict[date, MonthlyMovement]]:
    transaction_month = cast(
        func.date_trunc("month", TransactionRecord.process_date), Date
    ).label("transaction_month")
    signed_amount = case(
        (
            TransactionRecord.transaction_type.in_(policy.credit_types),
            TransactionRecord.amount,
        ),
        (
            TransactionRecord.transaction_type.in_(policy.debit_types),
            -TransactionRecord.amount,
        ),
        else_=Decimal("0"),
    )
    excluded_amount = case(
        (
            TransactionRecord.transaction_type.in_(policy.excluded_types),
            TransactionRecord.amount,
        ),
        else_=Decimal("0"),
    )
    excluded_count = case(
        (TransactionRecord.transaction_type.in_(policy.excluded_types), 1),
        else_=0,
    )
    statement = (
        select(
            TransactionRecord.product_id,
            transaction_month,
            func.sum(signed_amount).label("net_amount"),
            func.count().label("transaction_count"),
            func.sum(excluded_amount).label("excluded_amount"),
            func.sum(excluded_count).label("excluded_transaction_count"),
        )
        .where(TransactionRecord.source_kind == "source")
        .where(TransactionRecord.transaction_status == INCLUDED_STATUS)
        .group_by(TransactionRecord.product_id, transaction_month)
    )
    transaction_filter = _selected_transactions_filter(customer_ids)
    if transaction_filter is not None:
        statement = statement.where(transaction_filter)

    movements: dict[str, dict[date, MonthlyMovement]] = {}
    for (
        product_id,
        transaction_month_value,
        net_amount,
        transaction_count,
        excluded_amount_value,
        excluded_transaction_count,
    ) in session.exec(statement).all():
        movements.setdefault(product_id, {})[transaction_month_value] = MonthlyMovement(
            net_amount=net_amount,
            transaction_count=transaction_count,
            excluded_amount=excluded_amount_value,
            excluded_transaction_count=excluded_transaction_count,
        )
    return movements


def snapshot_rows(
    products: Iterable[Product],
    movements: dict[str, dict[date, MonthlyMovement]],
    anchor_date: date,
    start_month: date,
    end_month: date,
    calculated_at: datetime,
    transaction_policy: str,
) -> Iterable[dict[str, object]]:
    for product in products:
        if product.current_balance is None:
            raise ValueError(f"Product has no current balance: {product.product_id}")
        for value in build_snapshot_values(
            product.current_balance,
            anchor_date,
            movements.get(product.product_id, {}),
            start_month,
            end_month,
            product.opening_date,
        ):
            yield {
                "product_id": product.product_id,
                "snapshot_month": value.snapshot_month,
                "closing_balance": value.closing_balance,
                "currency": product.currency,
                "approved_transaction_count": value.approved_transaction_count,
                "net_transaction_amount": value.net_transaction_amount,
                "excluded_approved_transaction_count": (
                    value.excluded_approved_transaction_count
                ),
                "excluded_approved_transaction_amount": (
                    value.excluded_approved_transaction_amount
                ),
                "balance_uncertainty_amount": value.balance_uncertainty_amount,
                "anchor_balance": product.current_balance,
                "anchor_date": anchor_date,
                "calculation_method": CALCULATION_METHOD,
                "transaction_policy": transaction_policy,
                "calculated_at": calculated_at,
            }
