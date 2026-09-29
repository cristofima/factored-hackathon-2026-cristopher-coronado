"""Persistence access for BFF login identities."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from banking_shared.database import create_session
from banking_shared.models import Customer, Product, User
from sqlmodel import Session, select

SessionFactory = Callable[[], Session]


class UserRepository(Protocol):
    """Lookup contract used by the authentication boundary."""

    def find_by_email(self, email: str) -> User | None: ...

    def find_customer_name(self, user_id: str, customer_id: str) -> str | None: ...

    def list_accounts(self, user_id: str, customer_id: str) -> list[Product]: ...


class SqlModelUserRepository:
    """Read persisted login identities through SQLModel."""

    def __init__(self, session_factory: SessionFactory = create_session) -> None:
        self._session_factory = session_factory

    def find_by_email(self, email: str) -> User | None:
        with self._session_factory() as session:
            return session.exec(select(User).where(User.email == email)).one_or_none()

    def list_accounts(self, user_id: str, customer_id: str) -> list[Product]:
        with self._session_factory() as session:
            return list(session.exec(
                select(Product)
                .join(User, User.customer_id == Product.customer_id)
                .where(User.id == user_id, Product.customer_id == customer_id)
                .where(Product.product_type.in_(("Cuenta Ahorro", "Cuenta Corriente")))
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