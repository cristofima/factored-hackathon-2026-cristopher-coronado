"""Read-only integration checks against a seeded PostgreSQL database."""

import os

import pytest
from banking_shared.database import create_session
from banking_shared.models import Customer, Product, TransactionRecord
from sqlmodel import select

from services import TransactionService

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL is required for PostgreSQL integration tests",
)


def test_transactions_read_seeded_records_and_enforce_ownership() -> None:
    with create_session() as session:
        record = session.exec(
            select(TransactionRecord).order_by(
                TransactionRecord.transaction_date.desc(),
                TransactionRecord.transaction_id.desc(),
            )
        ).first()
        assert record is not None, "Seeded PostgreSQL must contain transactions"

        product = session.get(Product, record.product_id)
        assert product is not None
        assert product.customer_id == record.customer_id

        foreign_customer = session.exec(
            select(Customer)
            .where(Customer.customer_id != record.customer_id)
            .order_by(Customer.customer_id)
        ).first()
        assert foreign_customer is not None, "Cross-customer authorization needs two customers"

        product_id = record.product_id
        customer_id = record.customer_id
        foreign_customer_id = foreign_customer.customer_id

    service = TransactionService()

    transactions = service.get_transactions(product_id, customer_id)

    assert transactions
    assert all(transaction.accountId == product_id for transaction in transactions)
    with pytest.raises(PermissionError, match="authenticated customer"):
        service.get_transactions(product_id, foreign_customer_id)
    with pytest.raises(PermissionError, match="authenticated customer"):
        service.get_transactions("missing-product", customer_id)
