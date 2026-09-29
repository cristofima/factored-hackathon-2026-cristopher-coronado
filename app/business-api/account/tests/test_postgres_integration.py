"""Read-only integration checks against a seeded PostgreSQL database."""

import os

import pytest
from banking_shared.database import create_session
from banking_shared.models import Customer, Product
from sqlmodel import select

from services import ACCOUNT_PRODUCT_TYPES, AccountService

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL is required for PostgreSQL integration tests",
)


def test_account_reads_seeded_product_and_enforces_ownership() -> None:
    with create_session() as session:
        product = session.exec(
            select(Product)
            .where(Product.product_type.in_(ACCOUNT_PRODUCT_TYPES))
            .order_by(Product.product_id)
        ).first()
        assert product is not None, "Seeded PostgreSQL must contain an account product"

        foreign_customer = session.exec(
            select(Customer)
            .where(Customer.customer_id != product.customer_id)
            .order_by(Customer.customer_id)
        ).first()
        assert foreign_customer is not None, "Cross-customer authorization needs two customers"

        product_id = product.product_id
        customer_id = product.customer_id
        foreign_customer_id = foreign_customer.customer_id

    service = AccountService()

    account = service.get_account_details(product_id, customer_id)

    assert account is not None
    assert account.id == product_id
    with pytest.raises(PermissionError, match="authenticated customer"):
        service.get_account_details(product_id, foreign_customer_id)
    with pytest.raises(PermissionError, match="authenticated customer"):
        service.get_account_details("missing-product", customer_id)
