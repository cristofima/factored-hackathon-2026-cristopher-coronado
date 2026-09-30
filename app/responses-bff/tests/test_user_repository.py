"""Tests for persisted BFF user lookup."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from banking_shared.models import Customer, Product, User
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from bff.user_repository import SqlModelUserRepository


def _repository(
    first_name: str | None = " Mariana ", last_name: str | None = "Flores",
) -> SqlModelUserRepository:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Customer(
            customer_id="customer-1", email="demo@example.com",
            first_name=first_name, last_name=last_name,
        ))
        session.add(
            User(
                id="user-1",
                customer_id="customer-1",
                email="demo@example.com",
                password_hash="argon2-hash",
                locale="es",
            )
        )
        session.commit()
        session.add_all([
            Product(product_id="account-2", customer_id="customer-1",
                product_type="Checking Account", currency="USD"),
            Product(product_id="account-1", customer_id="customer-1",
                product_type="Savings Account", currency="USD"),
            Product(product_id="card-1", customer_id="customer-1",
                product_type="Credit Card", currency="USD"),
            Customer(customer_id="customer-2", email="other@example.com"),
        ])
        session.commit()
        session.add(Product(product_id="foreign-account", customer_id="customer-2",
                    product_type="Savings Account", currency="USD"))
        session.commit()

    @contextmanager
    def create_test_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    return SqlModelUserRepository(create_test_session)


def test_find_by_email_returns_persisted_user() -> None:
    user = _repository().find_by_email("demo@example.com")

    assert user is not None
    assert user.id == "user-1"
    assert user.customer_id == "customer-1"


def test_find_by_email_returns_none_for_unknown_email() -> None:
    assert _repository().find_by_email("missing@example.com") is None


def test_find_customer_name_returns_persisted_full_name() -> None:
    assert _repository().find_customer_name("user-1", "customer-1") == "Mariana Flores"


def test_find_customer_name_rejects_foreign_identity() -> None:
    repository = _repository()
    assert repository.find_customer_name("user-2", "customer-1") is None
    assert repository.find_customer_name("user-1", "customer-2") is None


def test_find_customer_name_handles_missing_name_parts() -> None:
    assert _repository(first_name=None).find_customer_name("user-1", "customer-1") == "Flores"
    assert _repository(first_name=" ", last_name=None).find_customer_name(
        "user-1", "customer-1"
    ) is None


def test_list_accounts_returns_only_owned_bank_accounts_in_order() -> None:
    accounts = _repository().list_accounts("user-1", "customer-1")
    assert [account.product_id for account in accounts] == ["account-1", "account-2"]


def test_list_accounts_does_not_return_accounts_for_foreign_identity() -> None:
    repository = _repository()
    assert repository.list_accounts("user-1", "customer-2") == []
    assert repository.list_accounts("user-2", "customer-1") == []