"""Ownership and storage mapping checks for Account services."""

import asyncio
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest
from banking_shared.models import Customer, Product, SQLModel
from banking_shared.product_types import PRODUCT_TYPE_LABELS
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp import Client
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

import mcp_tools
import routers
from internal_identity import get_http_customer_id
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
                    product_type="Checking Account",
                    product_number="ACCOUNT-SOURCE-NUMBER",
                    currency="USD",
                    current_balance=Decimal("1250.5000"),
                    opening_date=date(2024, 1, 2),
                    product_status="active",
                ),
                Product(
                    product_id="card-owned",
                    customer_id="customer-owned",
                    product_type="Credit Card",
                    product_number="4111111111111111",
                    currency="USD",
                    current_balance=Decimal("210.2500"),
                    credit_limit=Decimal("3000.0000"),
                    product_status="active",
                ),
                Product(
                    product_id="account-foreign",
                    customer_id="customer-foreign",
                    product_type="Savings Account",
                    currency="USD",
                ),
                Product(
                    product_id="card-foreign",
                    customer_id="customer-foreign",
                    product_type="Debit Card",
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

    account = account_service.get_account_details("ACCOUNT-SOURCE-NUMBER", "customer-owned")
    cards = card_service.get_credit_cards("ACCOUNT-SOURCE-NUMBER", "customer-owned")
    user_accounts = user_service.get_accounts_by_user_name(
        "owner@example.com",
        "customer-owned",
    )

    assert account is not None
    assert account.accountNumber == "ACCOUNT-SOURCE-NUMBER"
    assert user_accounts[0].accountNumber == "ACCOUNT-SOURCE-NUMBER"
    assert account.accountHolderFullName == "Ada Lovelace"
    assert account.balance == "1250.5000"
    assert [method.number for method in account.paymentMethods or []] == ["**** 1111"]
    assert len(cards) == 1
    assert "account-owned" not in account.model_dump_json()
    assert "card-owned" not in account.model_dump_json()
    assert cards[0].number == "**** 1111"
    assert cards[0].type == "credit"
    assert cards[0].name == "Credit Card"
    assert account.paymentMethods[0].type == "credit"
    assert "4111111111111111" not in cards[0].model_dump_json()
    assert cards[0].circuit is None
    assert len(user_accounts) == 1
    assert account_service.get_registered_beneficiary(
        "ACCOUNT-SOURCE-NUMBER",
        "customer-owned",
    ) == []


def test_foreign_product_numbers_are_denied(session_factory: Callable[[], Session]) -> None:
    with session_factory() as session:
        for product_id in ("account-foreign", "card-foreign"):
            product = session.get(Product, product_id)
            assert product is not None
            product.product_number = f"NUMBER-{product_id}"
            session.add(product)
        session.commit()

    with pytest.raises(PermissionError, match="authenticated customer"):
        AccountService(session_factory).get_account_details(
            "NUMBER-account-foreign", "customer-owned",
        )
    with pytest.raises(PermissionError, match="authenticated customer"):
        CardService(session_factory).get_card_details("NUMBER-card-foreign", "customer-owned")
    debit = CardService(session_factory).get_card_details(
        "NUMBER-card-foreign", "customer-foreign",
    )
    assert debit is not None
    assert debit.type == "debit"
    assert debit.name == "Debit Card"


@pytest.mark.parametrize(("canonical", "legacy"), PRODUCT_TYPE_LABELS.items())
def test_payment_method_type_is_normalized(
    session_factory: Callable[[], Session], canonical: str, legacy: str,
) -> None:
    for label in (canonical, legacy):
        with session_factory() as session:
            product = session.get(Product, "card-owned")
            assert product is not None
            product.product_type = label
            session.add(product)
            session.commit()

        method = AccountService(session_factory).get_payment_method_details(
            "4111111111111111", "customer-owned",
        )
        assert method is not None
        assert method.type == {"Credit Card": "credit", "Debit Card": "debit"}.get(
            canonical, canonical,
        )


@pytest.mark.parametrize(
    ("resource_id", "service_method"),
    [
        ("account-foreign", "account"),
        ("account-owned", "account"),
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


@pytest.mark.parametrize("number", [None, "", "   ", "1234", " 1234 ", "1234567890"])
def test_account_number_is_full_or_unavailable(
    session_factory: Callable[[], Session], number: str | None
) -> None:
    with session_factory() as session:
        product = session.get(Product, "account-owned")
        assert product is not None
        product.product_number = number
        session.add(product)
        session.commit()

    account = UserService(session_factory).get_accounts_by_user_name(
        "owner@example.com", "customer-owned"
    )[0]

    assert account is not None
    assert account.accountNumber == ((number.strip() or None) if number else None)


def test_duplicate_owned_numbers_are_denied(session_factory: Callable[[], Session]) -> None:
    with session_factory() as session:
        session.add(Product(
            product_id="duplicate", customer_id="customer-owned",
            product_type="Savings Account", currency="USD",
            product_number="ACCOUNT-SOURCE-NUMBER",
        ))
        session.commit()

    with pytest.raises(PermissionError, match="authenticated customer"):
        AccountService(session_factory).get_account_details(
            "ACCOUNT-SOURCE-NUMBER", "customer-owned",
        )


def test_mcp_number_lookup_returns_full_account_without_primary_keys(
    session_factory: Callable[[], Session], monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mcp_tools, "account_service", AccountService(session_factory))
    monkeypatch.setattr(mcp_tools, "get_customer_id", lambda headers: "customer-owned")

    async def call_account_tool() -> None:
        async with Client(mcp_tools.mcp) as client:
            result = await client.call_tool(
                "getAccountDetails", {"product_number": "ACCOUNT-SOURCE-NUMBER"},
            )
        assert not result.is_error
        text = " ".join(content.text for content in result.content)
        assert "ACCOUNT-SOURCE-NUMBER" in text
        assert "account-owned" not in text
        assert "card-owned" not in text
        assert "4111111111111111" not in text

    asyncio.run(call_account_tool())


def test_foreign_user_name_is_denied(session_factory: Callable[[], Session]) -> None:
    with pytest.raises(PermissionError, match="authenticated customer"):
        UserService(session_factory).get_accounts_by_user_name(
            "foreign@example.com",
            "customer-owned",
        )


@pytest.mark.parametrize("resource_id", ["account-foreign", "missing-product"])
def test_mcp_account_denial_preserves_error_without_resource_data(
    session_factory: Callable[[], Session],
    monkeypatch: pytest.MonkeyPatch,
    resource_id: str,
) -> None:
    monkeypatch.setattr(mcp_tools, "account_service", AccountService(session_factory))
    monkeypatch.setattr(mcp_tools, "get_customer_id", lambda headers: "customer-owned")

    async def call_account_tool() -> None:
        async with Client(mcp_tools.mcp) as client:
            result = await client.call_tool(
                "getAccountDetails", {"product_number": resource_id}, raise_on_error=False,
            )
        assert result.is_error is True
        assert result.structured_content is None
        assert len(result.content) == 1
        assert result.content[0].text == (
            "Error calling tool 'getAccountDetails': "
            "Account does not belong to the authenticated customer"
        )

    asyncio.run(call_account_tool())


@pytest.mark.parametrize("resource_id", ["account-foreign", "missing-product"])
def test_rest_account_cards_denial_returns_403(
    session_factory: Callable[[], Session],
    monkeypatch: pytest.MonkeyPatch,
    resource_id: str,
) -> None:
    monkeypatch.setattr(routers, "card_service_singleton", CardService(session_factory))
    app = FastAPI()
    app.include_router(routers.router, prefix="/api")
    app.dependency_overrides[get_http_customer_id] = lambda: "customer-owned"

    with TestClient(app) as client:
        response = client.get(f"/api/accounts/{resource_id}/cards")

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Account does not belong to the authenticated customer",
    }
