"""Ownership and storage mapping checks for Transaction services."""

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from banking_shared.models import Customer, Product, SQLModel, TransactionRecord
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from services import TransactionService


@pytest.fixture
def session_factory() -> Callable[[], Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                Customer(customer_id="customer-owned", email="owner@example.com"),
                Customer(customer_id="customer-foreign", email="foreign@example.com"),
                Product(
                    product_id="account-owned",
                    product_number="ACCOUNT-NUMBER",
                    customer_id="customer-owned",
                    product_type="Checking Account",
                    currency="USD",
                ),
                Product(
                    product_id="card-owned",
                    product_number="4111111111111111",
                    customer_id="customer-owned",
                    product_type="Credit Card",
                    currency="USD",
                ),
                Product(
                    product_id="account-foreign",
                    product_number="FOREIGN-NUMBER",
                    customer_id="customer-foreign",
                    product_type="Savings Account",
                    currency="USD",
                ),
                Product(
                    product_id="card-foreign",
                    product_number="5555555555554444",
                    customer_id="customer-foreign",
                    product_type="Debit Card",
                    currency="USD",
                ),
            ]
        )
        base_time = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
        session.add_all(
            [
                TransactionRecord(
                    transaction_id=f"account-tx-{index}",
                    transaction_date=base_time + timedelta(days=index),
                    process_date=date(2026, 6, index + 1),
                    product_id="account-owned",
                    customer_id="customer-owned",
                    transaction_type="payment" if index % 2 else "deposit",
                    transaction_category="Utilities",
                    amount=Decimal(f"{100 + index}.2500"),
                    currency="USD",
                    channel="BankTransfer",
                    merchant_name="ACME Energy" if index == 5 else "Other Merchant",
                    transaction_status="approved",
                )
                for index in range(6)
            ]
        )
        session.add(
            TransactionRecord(
                transaction_id="card-tx-1",
                transaction_date=base_time + timedelta(days=10),
                process_date=date(2026, 6, 11),
                product_id="card-owned",
                customer_id="customer-owned",
                transaction_type="purchase",
                transaction_category="Retail",
                amount=Decimal("42.5000"),
                currency="USD",
                channel="CreditCard",
                merchant_name="Contoso Store",
                transaction_status="approved",
            )
        )
        session.add(
            TransactionRecord(
                transaction_id="inconsistent-owner",
                transaction_date=base_time + timedelta(days=20),
                process_date=date(2026, 6, 21),
                product_id="account-owned",
                customer_id="customer-foreign",
                transaction_type="payment",
                amount=Decimal("999.0000"),
                currency="USD",
            )
        )
        session.commit()
    return lambda: Session(engine)


def test_last_transactions_are_owned_limited_and_ordered(
    session_factory: Callable[[], Session],
) -> None:
    transactions = TransactionService(session_factory).get_transactions(
        "ACCOUNT-NUMBER",
        "customer-owned",
    )

    assert [transaction.id for transaction in transactions] == [
        "account-tx-5",
        "account-tx-4",
        "account-tx-3",
        "account-tx-2",
        "account-tx-1",
    ]
    assert all(transaction.id != "inconsistent-owner" for transaction in transactions)
    assert transactions[0].recipientName == "ACME Energy"
    assert transactions[0].amount == 105.25
    assert transactions[0].product_number == "ACCOUNT-NUMBER"
    assert "account-owned" not in transactions[0].model_dump_json()


def test_recipient_and_type_filters_use_persisted_fields(
    session_factory: Callable[[], Session],
) -> None:
    service = TransactionService(session_factory)

    recipient_matches = service.get_transactions_by_recipient_name(
        "ACCOUNT-NUMBER",
        "acme",
        "customer-owned",
    )
    type_matches = service.get_transactions_by_type(
        "ACCOUNT-NUMBER",
        "customer-owned",
        payment_type="BankTransfer",
        transaction_type="payment",
    )

    assert [transaction.id for transaction in recipient_matches] == ["account-tx-5"]
    assert [transaction.id for transaction in type_matches] == [
        "account-tx-5",
        "account-tx-3",
        "account-tx-1",
    ]


def test_duplicate_owned_numbers_are_denied(session_factory: Callable[[], Session]) -> None:
    with session_factory() as session:
        session.add(Product(
            product_id="duplicate", customer_id="customer-owned",
            product_type="Savings Account", currency="USD", product_number="ACCOUNT-NUMBER",
        ))
        session.commit()

    with pytest.raises(PermissionError, match="authenticated customer"):
        TransactionService(session_factory).get_transactions("ACCOUNT-NUMBER", "customer-owned")


def test_card_transactions_require_both_owned_products(
    session_factory: Callable[[], Session],
) -> None:
    service = TransactionService(session_factory)

    transactions = service.get_transactions_by_type(
        "ACCOUNT-NUMBER",
        "customer-owned",
        card_id="4111111111111111",
    )

    assert [transaction.id for transaction in transactions] == ["card-tx-1"]
    assert transactions[0].product_number == "**** 1111"
    assert "card-owned" not in transactions[0].model_dump_json()

    with pytest.raises(PermissionError, match="authenticated customer"):
        service.get_transactions_by_type(
            "ACCOUNT-NUMBER",
            "customer-owned",
            card_id="5555555555554444",
        )


@pytest.mark.parametrize("product_id", ["FOREIGN-NUMBER", "account-owned", "account-foreign", "missing-product"])
def test_foreign_and_missing_products_are_indistinguishable(
    session_factory: Callable[[], Session],
    product_id: str,
) -> None:
    with pytest.raises(PermissionError, match="authenticated customer"):
        TransactionService(session_factory).get_transactions(
            product_id,
            "customer-owned",
        )


@pytest.mark.parametrize("label", ("Debit Card", "Tarjeta D\u00e9bito"))
def test_owned_debit_card_transactions_are_masked(
    session_factory: Callable[[], Session], label: str,
) -> None:
    with session_factory() as session:
        product = session.get(Product, "card-owned")
        assert product is not None
        product.product_type = label
        session.add(product)
        session.commit()

    if label != "Debit Card":
        with pytest.raises(PermissionError, match="authenticated customer"):
            TransactionService(session_factory).get_transactions_by_type(
                "ACCOUNT-NUMBER", "customer-owned", card_id="4111111111111111",
            )
        return

    transactions = TransactionService(session_factory).get_transactions_by_type(
        "ACCOUNT-NUMBER", "customer-owned", card_id="4111111111111111",
    )

    assert [transaction.id for transaction in transactions] == ["card-tx-1"]
    assert transactions[0].product_number == "**** 1111"
