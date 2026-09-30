"""Ownership and storage mapping checks for Account services."""

from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest
from banking_shared.models import Customer, Product, SQLModel
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

from services import AccountService, CardService, UserService


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
                Customer(
                    customer_id="customer-owned",
                    email="owner@example.com",
                    first_name="Ada",
                    last_name="Lovelace",
                ),
                Customer(
                    customer_id="customer-foreign",
                    email="foreign@example.com",
                    first_name="Grace",
                    last_name="Hopper",
                ),
                Product(
                    product_id="account-owned",
                    customer_id="customer-owned",
                    product_type="Cuenta Corriente",
                    product_number="ACCOUNT-SOURCE-NUMBER",
                    currency="USD",
                    current_balance=Decimal("1250.5000"),
                    opening_date=date(2024, 1, 2),
                    product_status="active",
                ),
                Product(
                    product_id="card-owned",
                    customer_id="customer-owned",
                    product_type="Tarjeta Cr\u00e9dito",
                    product_number="4111111111111111",
                    currency="USD",
                    current_balance=Decimal("210.2500"),
                    credit_limit=Decimal("3000.0000"),
                    product_status="active",
                ),
                Product(
                    product_id="account-foreign",
                    customer_id="customer-foreign",
                    product_type="Cuenta Ahorro",
                    currency="USD",
                ),
                Product(
                    product_id="card-foreign",
                    customer_id="customer-foreign",
                    product_type="Tarjeta D\u00e9bito",
                    currency="USD",
                ),
            ]
        )
        session.commit()
    return lambda: Session(engine)


def test_owned_account_resources_are_mapped_from_storage(
    session_factory: Callable[[], Session],
) -> None:
    account_service = AccountService(session_factory)
    card_service = CardService(session_factory)
    user_service = UserService(session_factory)

    account = account_service.get_account_details("account-owned", "customer-owned")
    cards = card_service.get_credit_cards("account-owned", "customer-owned")
    user_accounts = user_service.get_accounts_by_user_name(
        "owner@example.com",
        "customer-owned",
    )

    assert account is not None
    assert account.accountHolderFullName == "Ada Lovelace"
    assert account.balance == "1250.5000"
    assert [method.id for method in account.paymentMethods or []] == ["card-owned"]
    assert [card.id for card in cards] == ["card-owned"]
    assert cards[0].number is None
    assert cards[0].circuit is None
    assert [owned_account.id for owned_account in user_accounts] == ["account-owned"]
    assert account_service.get_registered_beneficiary(
        "account-owned",
        "customer-owned",
    ) == []


@pytest.mark.parametrize(
    ("resource_id", "service_method"),
    [
        ("account-foreign", "account"),
        ("card-foreign", "card"),
        ("missing-product", "account"),
    ],
)
def test_foreign_and_missing_resources_are_indistinguishable(
    session_factory: Callable[[], Session],
    resource_id: str,
    service_method: str,
) -> None:
    if service_method == "card":
        operation = lambda: CardService(session_factory).get_card_details(
            resource_id,
            "customer-owned",
        )
    else:
        operation = lambda: AccountService(session_factory).get_account_details(
            resource_id,
            "customer-owned",
        )

    with pytest.raises(PermissionError, match="authenticated customer"):
        operation()


def test_foreign_user_name_is_denied(session_factory: Callable[[], Session]) -> None:
    with pytest.raises(PermissionError, match="authenticated customer"):
        UserService(session_factory).get_accounts_by_user_name(
            "foreign@example.com",
            "customer-owned",
        )
