from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, time

from banking_shared.database import create_session
from banking_shared.models import Product, TransactionRecord
from banking_shared.product_types import CARD_PRODUCT_TYPES
from models import Transaction
from sqlalchemy import func
from sqlmodel import Session, select
from sqlmodel.sql.expression import SelectOfScalar

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


class TransactionService:
    def __init__(self, session_factory: SessionFactory = create_session) -> None:
        self._session_factory = session_factory

    def get_transactions_by_recipient_name(
        self,
        account_id: str,
        name: str,
        customer_id: str,
    ) -> list[Transaction]:
        logger.info(
            "get_transactions_by_recipient_name called with account_id=%s, name=%s",
            account_id,
            name,
        )
        _require_identifier(name, "RecipientName")
        with self._session_factory() as session:
            product = _get_owned_product(session, account_id, customer_id)
            statement = _transaction_statement(product.product_id, customer_id).where(
                TransactionRecord.merchant_name.ilike(f"%{name.strip()}%")
            )
            return _execute_transactions(session, statement, product)

    def get_transactions(self, account_id: str, customer_id: str) -> list[Transaction]:
        logger.info("get_last_transactions called with account_id=%s", account_id)
        with self._session_factory() as session:
            product = _get_owned_product(session, account_id, customer_id)
            statement = _transaction_statement(product.product_id, customer_id).limit(5)
            return _execute_transactions(session, statement, product)

    def get_transactions_by_type(
        self,
        account_id: str,
        customer_id: str,
        payment_type: str | None = None,
        transaction_type: str | None = None,
        card_id: str | None = None,
    ) -> list[Transaction]:
        logger.info(
            "get_transactions_by_type called with account_id=%s, payment_type=%s, transaction_type=%s, card_id=%s",
            account_id,
            payment_type,
            transaction_type,
            card_id,
        )
        with self._session_factory() as session:
            _get_owned_product(session, account_id, customer_id)
            product = (
                _get_owned_product(session, card_id, customer_id, CARD_PRODUCT_TYPES)
                if card_id
                else _get_owned_product(session, account_id, customer_id)
            )
            statement = _transaction_statement(product.product_id, customer_id)
            if transaction_type:
                statement = statement.where(
                    TransactionRecord.transaction_type == transaction_type
                )
            if payment_type:
                statement = statement.where(TransactionRecord.channel == payment_type)
            return _execute_transactions(session, statement, product)

    def notify_transaction(
        self,
        account_id: str,
        transaction: Transaction,
        customer_id: str,
    ) -> None:
        logger.info("notify_transaction called with account_id=%s", account_id)
        if transaction.product_number not in (None, account_id):
            raise ValueError("Transaction product_number does not match the requested number")
        with self._session_factory() as session:
            _get_owned_product(session, account_id, customer_id)
        raise RuntimeError("Transaction creation is unavailable for persisted records")

    def get_transaction_history(
        self,
        account_id: str,
        customer_id: str,
        start_date: date | None,
        end_date: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Transaction], int]:
        logger.info(
            "get_transaction_history called with account_id=%s, start_date=%s, end_date=%s",
            account_id,
            start_date,
            end_date,
        )
        with self._session_factory() as session:
            product = _get_owned_product(session, account_id, customer_id)
            statement = _transaction_statement(product.product_id, customer_id)
            if start_date is not None:
                statement = statement.where(
                    TransactionRecord.transaction_date >= datetime.combine(start_date, time.min)
                )
            if end_date is not None:
                statement = statement.where(
                    TransactionRecord.transaction_date <= datetime.combine(end_date, time.max)
                )
            total = session.exec(select(func.count()).select_from(statement.subquery())).one()
            records = session.exec(statement.limit(limit).offset(offset)).all()
            return [_to_transaction(record, product) for record in records], total


transaction_service_singleton = TransactionService()


def _require_identifier(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} is empty or null")


def _get_owned_product(
    session: Session,
    product_id: str,
    customer_id: str,
    product_types: tuple[str, ...] | None = None,
) -> Product:
    _require_identifier(product_id, "AccountId")
    statement = (
        select(Product)
        .where(Product.product_number == product_id)
        .where(Product.customer_id == customer_id)
    )
    if product_types is not None:
        statement = statement.where(Product.product_type.in_(product_types))
    products = session.exec(statement.limit(2)).all()
    if len(products) != 1:
        raise PermissionError("Account does not belong to the authenticated customer")
    return products[0]


def _transaction_statement(
    product_id: str,
    customer_id: str,
) -> SelectOfScalar[TransactionRecord]:
    return (
        select(TransactionRecord)
        .where(TransactionRecord.product_id == product_id)
        .where(TransactionRecord.customer_id == customer_id)
        .order_by(
            TransactionRecord.transaction_date.desc(),
            TransactionRecord.transaction_id.desc(),
        )
    )


def _execute_transactions(
    session: Session,
    statement: SelectOfScalar[TransactionRecord],
    product: Product,
) -> list[Transaction]:
    return [
        _to_transaction(record, product)
        for record in session.exec(statement).all()
    ]


def _to_transaction(record: TransactionRecord, product: Product) -> Transaction:
    product_number = product.product_number
    if product.product_type in CARD_PRODUCT_TYPES:
        product_number = (
            f"**** {product_number[-4:]}"
            if product_number and len(product_number) > 4 else None
        )
    return Transaction(
        id=record.transaction_id,
        type=record.transaction_type,
        recipientName=record.merchant_name,
        product_number=product_number,
        paymentType=record.channel,
        amount=float(record.amount),
        currency=record.currency,
        timestamp=record.transaction_date.isoformat(),
        category=record.transaction_category,
        status=record.transaction_status,
    )
