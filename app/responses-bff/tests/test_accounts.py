"""SQLite-backed contract tests for authenticated account reads."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import jwt
import pytest
from banking_shared.models import Customer, Product, TransactionRecord, User
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from bff.main import create_app
from bff.settings import Settings
from bff.user_repository import SqlModelUserRepository

TEST_SECRET = "test-secret-key-with-at-least-32-bytes"


def _headers(user_id: str = "user-1", customer_id: str = "customer-1") -> dict[str, str]:
    settings = _settings()
    token = jwt.encode({
        "sub": user_id, "customer_id": customer_id, "email": "demo@example.com",
        "locale": "es", "iss": settings.jwt_issuer, "aud": settings.jwt_audience,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }, TEST_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


def _settings() -> Settings:
    return Settings(
        _env_file=None, responses_upstream_mode="local", jwt_secret_key=TEST_SECRET,
    )


@pytest.fixture
def repository() -> Iterator[SqlModelUserRepository]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Customer(customer_id="customer-1", email="demo@example.com"),
            Customer(customer_id="customer-2", email="other@example.com"),
        ])
        session.commit()
        session.add_all([
            User(id="user-1", customer_id="customer-1", email="demo@example.com",
                 password_hash="unused", locale="es"),
            User(id="user-2", customer_id="customer-2", email="other@example.com",
                 password_hash="unused", locale="pt"),
            Product(product_id="account-1", customer_id="customer-1",
                    product_number="NUMBER-1",
                    product_type="Cuenta Ahorro", currency="USD",
                    current_balance=Decimal("12345678.9012")),
            Product(product_id="empty", customer_id="customer-1",
                    product_number="NUMBER-EMPTY",
                    product_type="Cuenta Corriente", currency="USD"),
            Product(product_id="card", customer_id="customer-1",
                    product_type="Tarjeta", currency="USD"),
            Product(product_id="foreign", customer_id="customer-2",
                    product_number="NUMBER-FOREIGN",
                    product_type="Cuenta Ahorro", currency="EUR"),
                Product(product_id="credit", customer_id="customer-1",
                    product_type="Tarjeta Cr\u00e9dito", currency="USD",
                    product_number="1234567890123456", current_balance=Decimal("12.3456"),
                    credit_limit=Decimal("1000.0000"), expiration_date=date(2028, 1, 1)),
                Product(product_id="debit", customer_id="customer-1",
                    product_type="Tarjeta D\u00e9bito", currency="EUR"),
                Product(product_id="foreign-card", customer_id="customer-2",
                    product_type="Tarjeta Cr\u00e9dito", currency="EUR"),
        ])
        session.commit()
        timestamps = [
            ("before", "2026-05-31T23:59:59.999999"),
            ("first", "2026-06-01T00:00:00"),
            ("tie-a", "2026-06-01T12:00:00"),
            ("tie-b", "2026-06-01T12:00:00"),
            ("last", "2026-06-01T23:59:59.999999"),
            ("after", "2026-06-02T00:00:00"),
        ]
        for transaction_id, timestamp in timestamps:
            session.add(TransactionRecord(
                transaction_id=transaction_id, transaction_date=datetime.fromisoformat(timestamp),
                process_date=date(2026, 6, 3), product_id="account-1", customer_id="customer-1",
                amount=Decimal("-123456.7891"), currency="USD",
            ))
        session.add_all([
            TransactionRecord(
                transaction_id="wrong-customer", transaction_date=datetime(2026, 6, 1, 18),
                process_date=date(2026, 6, 1), product_id="account-1", customer_id="customer-2",
                amount=Decimal("1"), currency="USD",
            ),
            TransactionRecord(
                transaction_id="wrong-product", transaction_date=datetime(2026, 6, 1, 18),
                process_date=date(2026, 6, 1), product_id="foreign", customer_id="customer-1",
                amount=Decimal("1"), currency="USD",
            ),
        ])
        session.commit()
    yield SqlModelUserRepository(lambda: Session(engine))
    engine.dispose()


@pytest.fixture
def client(repository: SqlModelUserRepository) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(), user_repository=repository)) as client:
        yield client


def test_account_balance_preserves_decimal_and_null(client: TestClient) -> None:
    response = client.get("/auth/me/accounts", headers=_headers())

    assert response.status_code == 200
    assert [(item["number"], item["balance"]) for item in response.json()] == [
        ("NUMBER-1", "12345678.9012"), ("NUMBER-EMPTY", None),
    ]
    assert all("id" not in item for item in response.json())


def test_cards_preserve_fields_mask_number_and_filter_products(client: TestClient) -> None:
    response = client.get("/auth/me/cards?customer_id=customer-2", headers=_headers())
    assert response.status_code == 200
    assert response.json() == [
        {"type": "Tarjeta Cr\u00e9dito", "currency": "USD",
         "status": None, "opened": None, "number": "**** 3456", "balance": "12.3456",
         "expires": "2028-01-01", "credit_limit": "1000.0000"},
        {"type": "Tarjeta D\u00e9bito", "currency": "EUR",
         "status": None, "opened": None, "number": None, "balance": None,
         "expires": None, "credit_limit": None},
    ]
    other = client.get("/auth/me/cards", headers=_headers("user-2", "customer-2"))
    assert len(other.json()) == 1
    assert all("id" not in item for item in other.json())


@pytest.mark.parametrize(("user_id", "customer_id"), [
    ("user-1", "customer-2"), ("user-2", "customer-1"), ("missing", "customer-1"),
])
def test_cards_reject_mismatched_persisted_identity(
    client: TestClient, user_id: str, customer_id: str,
) -> None:
    response = client.get("/auth/me/cards", headers=_headers(user_id, customer_id))
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid"}])
def test_cards_require_valid_bearer(client: TestClient, headers: dict[str, str]) -> None:
    assert client.get("/auth/me/cards", headers=headers).status_code == 401


def test_cards_empty_and_database_failure() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with TestClient(create_app(
        _settings(), user_repository=SqlModelUserRepository(lambda: Session(engine)),
    )) as client:
        response = client.get("/auth/me/cards", headers=_headers())
        assert response.status_code == 200
        assert response.json() == []
    engine.dispose()

    def failed_session() -> Session:
        raise SQLAlchemyError("Unavailable")

    with TestClient(create_app(
        _settings(), user_repository=SqlModelUserRepository(failed_session),
    )) as client:
        response = client.get("/auth/me/cards", headers=_headers())
    assert response.status_code == 503
    assert response.json() == {"detail": "Cards are temporarily unavailable"}


def test_transactions_date_boundaries_order_precision_and_nulls(client: TestClient) -> None:
    response = client.get(
        "/accounts/NUMBER-1/transactions?start_date=2026-06-01&end_date=2026-06-01",
        headers=_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "items": [{
            "id": transaction_id, "product_number": "NUMBER-1", "date": timestamp,
            "amount": "-123456.7891", "currency": "USD", "type": None,
            "category": None, "channel": None, "merchant": None, "status": None,
        } for transaction_id, timestamp in [
            ("last", "2026-06-01T23:59:59.999999"), ("tie-b", "2026-06-01T12:00:00"),
            ("tie-a", "2026-06-01T12:00:00"), ("first", "2026-06-01T00:00:00"),
        ]],
        "total": 4, "limit": 100, "offset": 0,
        "start_date": "2026-06-01", "end_date": "2026-06-01",
    }


@pytest.mark.parametrize(("query", "expected_ids", "total"), [
    ("", ["after", "last", "tie-b", "tie-a", "first", "before"], 6),
    ("?start_date=2026-06-01", ["after", "last", "tie-b", "tie-a", "first"], 5),
    ("?end_date=2026-06-01", ["last", "tie-b", "tie-a", "first", "before"], 5),
    ("?limit=2&offset=2", ["tie-b", "tie-a"], 6),
    ("?offset=99", [], 6),
    ("?start_date=2027-01-01", [], 0),
    ("?end_date=9999-12-31", ["after", "last", "tie-b", "tie-a", "first", "before"], 6),
])
def test_transactions_pagination_and_optional_dates(
    client: TestClient, query: str, expected_ids: list[str], total: int,
) -> None:
    response = client.get(f"/accounts/NUMBER-1/transactions{query}", headers=_headers())

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == expected_ids
    assert body["total"] == total
    assert body["limit"] == (2 if "limit=2" in query else 100)
    assert body["offset"] == (2 if "offset=2" in query else 99 if "offset=99" in query else 0)


@pytest.mark.parametrize(("account_id", "user_id", "customer_id"), [
    ("NUMBER-FOREIGN", "user-1", "customer-1"), ("account-1", "user-1", "customer-1"),
    ("foreign", "user-1", "customer-1"), ("missing", "user-1", "customer-1"),
    ("card", "user-1", "customer-1"), ("account-1", "user-2", "customer-1"),
    ("foreign", "user-1", "customer-2"), ("account-1", "missing", "customer-1"),
])
def test_transactions_requires_both_identity_claims_and_bank_account(
    client: TestClient, account_id: str, user_id: str, customer_id: str,
) -> None:
    response = client.get(
        f"/accounts/{account_id}/transactions", headers=_headers(user_id, customer_id),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Account not found"}


def test_empty_owned_account_returns_success(client: TestClient) -> None:
    response = client.get("/accounts/NUMBER-EMPTY/transactions", headers=_headers())

    assert response.status_code == 200
    assert response.json() == {
        "items": [], "total": 0, "limit": 100, "offset": 0,
        "start_date": None, "end_date": None,
    }


def test_duplicate_account_numbers_are_denied(
    client: TestClient, repository: SqlModelUserRepository,
) -> None:
    with repository._session_factory() as session:
        session.add(Product(
            product_id="duplicate", customer_id="customer-1", product_number="NUMBER-1",
            product_type="Cuenta Ahorro", currency="USD",
        ))
        session.commit()

    response = client.get("/accounts/NUMBER-1/transactions", headers=_headers())

    assert response.status_code == 404
    assert response.json() == {"detail": "Account not found"}


@pytest.mark.parametrize("number", ["", "1234", "1234567890123456"])
def test_debit_card_number_is_masked_or_unavailable(
    client: TestClient, repository: SqlModelUserRepository, number: str,
) -> None:
    with repository._session_factory() as session:
        card = session.get(Product, "debit")
        assert card is not None
        card.product_number = number
        session.add(card)
        session.commit()

    response = client.get("/auth/me/cards", headers=_headers())

    assert response.status_code == 200
    debit = next(item for item in response.json() if item["type"] == "Tarjeta D\u00e9bito")
    assert debit["number"] == ("**** 3456" if len(number) > 4 else None)
    assert "id" not in debit


@pytest.mark.parametrize("query", [
    "limit=101", "limit=0", "limit=-1", "limit=abc", "offset=-1", "offset=1.5",
    "start_date=invalid", "end_date=2026-02-30",
    "start_date=2026-06-02&end_date=2026-06-01",
])
def test_transactions_rejects_invalid_queries(client: TestClient, query: str) -> None:
    response = client.get(f"/accounts/account-1/transactions?{query}", headers=_headers())

    assert response.status_code == 422


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid"}])
def test_transactions_requires_valid_jwt(client: TestClient, headers: dict[str, str]) -> None:
    response = client.get("/accounts/account-1/transactions", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("error", [RuntimeError("Unavailable"), SQLAlchemyError("Unavailable")])
def test_transactions_database_failure_returns_503(error: Exception) -> None:
    def failed_session() -> Session:
        raise error

    repository = SqlModelUserRepository(failed_session)
    with TestClient(create_app(_settings(), user_repository=repository)) as client:
        response = client.get("/accounts/account-1/transactions", headers=_headers())

    assert response.status_code == 503
    assert response.json() == {"detail": "Transactions are temporarily unavailable"}