"""Persistence access for BFF login identities."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time
from typing import Protocol

from banking_shared.database import create_session
from banking_shared.models import Customer, Product, TransactionRecord, User
from banking_shared.product_types import ACCOUNT_PRODUCT_TYPES, CARD_PRODUCT_TYPES
from sqlalchemy import func
from sqlmodel import Session, select

SessionFactory = Callable[[], Session]


class UserRepository(Protocol):
    """Lookup contract used by the authentication boundary."""

    def find_by_email(self, email: str) -> User | None: ...

    def find_customer_name(self, user_id: str, customer_id: str) -> str | None: ...

    def list_accounts(self, user_id: str, customer_id: str) -> list[Product]: ...

    def list_cards(self, user_id: str, customer_id: str) -> list[Product]: ...

    def list_transactions(
        self, user_id: str, customer_id: str, account_id: str,
        start_date: date | None, end_date: date | None, limit: int, offset: int,
    ) -> tuple[list[TransactionRecord], int] | None: ...


class SqlModelUserRepository:
    """Read persisted login identities through SQLModel."""

    def __init__(self, session_factory: SessionFactory = create_session) -> None:
        self._session_factory = session_factory

    def find_by_email(self, email: str) -> User | None:
        with self._session_factory() as session:
            return session.exec(select(User).where(User.email == email)).one_or_none()

    def list_transactions(
        self, user_id: str, customer_id: str, account_id: str,
        start_date: date | None, end_date: date | None, limit: int, offset: int,
    ) -> tuple[list[TransactionRecord], int] | None:
        with self._session_factory() as session:
            accounts = session.exec(
                select(Product)
                .join(User, User.customer_id == Product.customer_id)
                .where(User.id == user_id, Product.customer_id == customer_id)
                .where(Product.product_number == account_id)
                .where(Product.product_type.in_(ACCOUNT_PRODUCT_TYPES))
                .limit(2)
            ).all()
            if len(accounts) != 1:
                return None
            account = accounts[0]
            query = select(TransactionRecord).where(
                TransactionRecord.product_id == account.product_id,
                TransactionRecord.customer_id == customer_id,
            )
            if start_date is not None:
                query = query.where(
                    TransactionRecord.transaction_date >= datetime.combine(start_date, time.min)
                )
            if end_date is not None:
                query = query.where(
                    TransactionRecord.transaction_date <= datetime.combine(end_date, time.max)
                )
            total = session.exec(select(func.count()).select_from(query.subquery())).one()
            items = session.exec(
                query.order_by(
                    TransactionRecord.transaction_date.desc(),
                    TransactionRecord.transaction_id.desc(),
                ).limit(limit).offset(offset)
            ).all()
            return list(items), total

    def list_accounts(self, user_id: str, customer_id: str) -> list[Product]:
        with self._session_factory() as session:
            return list(session.exec(
                select(Product)
                .join(User, User.customer_id == Product.customer_id)
                .where(User.id == user_id, Product.customer_id == customer_id)
                .where(Product.product_type.in_(ACCOUNT_PRODUCT_TYPES))
                .order_by(Product.product_id)
            ).all())

    def list_cards(self, user_id: str, customer_id: str) -> list[Product]:
        with self._session_factory() as session:
            return list(session.exec(
                select(Product)
                .join(User, User.customer_id == Product.customer_id)
                .where(User.id == user_id, Product.customer_id == customer_id)
                .where(Product.product_type.in_(CARD_PRODUCT_TYPES))
                .order_by(Product.product_id)
            ).all())

    def find_customer_name(self, user_id: str, customer_id: str) -> str | None:
        with self._session_factory() as session:
            customer = session.exec(
                select(Customer)
                .join(User, User.customer_id == Customer.customer_id)
                .where(User.id == user_id, Customer.customer_id == customer_id)
            ).one_or_none()
            if customer is None:
                return None
            name = " ".join(
                part.strip() for part in (customer.first_name, customer.last_name)
                if part and part.strip()
            )
            return name or None