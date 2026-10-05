from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from banking_shared.models import Customer, Product, SQLModel, TransactionRecord
from sqlalchemy import func
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from banking_transaction.services.transactions import TransactionService

SELECTED_DATE = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)


@pytest.fixture
def recognition_sessions() -> Callable[[], Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    engine = engine.execution_options(schema_translate_map={"support": None})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            Customer(customer_id="owner", email="owner@example.com"),
            Customer(customer_id="foreign", email="foreign@example.com"),
            Product(product_id="card", product_number="4111111111111111",
                    customer_id="owner", product_type="Credit Card", currency="USD"),
            Product(product_id="other-card", product_number="5555555555554444",
                    customer_id="owner", product_type="Debit Card", currency="USD"),
            Product(product_id="foreign-card", product_number="5555555555553333",
                    customer_id="foreign", product_type="Debit Card", currency="USD"),
            Product(product_id="bank", product_number="ACCOUNT", customer_id="owner",
                    product_type="Checking Account", currency="USD"),
            _record("selected", 0),
        ])
        session.commit()
    return lambda: Session(engine)


def _record(identifier: str, days: int, **overrides: Any) -> TransactionRecord:
    values: dict[str, Any] = {
        "transaction_id": identifier, "transaction_date": SELECTED_DATE + timedelta(days=days),
        "process_date": date(2026, 6, 1), "product_id": "card", "customer_id": "owner",
        "amount": Decimal("42.1234"), "currency": "USD", "merchant_name": "Cafe",
        "transaction_type": "Purchase", "transaction_status": "Approved",
    }
    values.update(overrides)
    return TransactionRecord(**values)


def test_exact_matches_are_stable_capped_and_read_only(
    recognition_sessions: Callable[[], Session],
) -> None:
    with recognition_sessions() as session:
        session.add_all([_record(name, -1, merchant_name="  cAfE  ") for name in "abcd"])
        session.add(_record("lower-bound", -180))
        session.commit()
        before = {table.name: session.exec(select(func.count()).select_from(table)).one()
                  for table in SQLModel.metadata.sorted_tables}
    result = TransactionService(recognition_sessions).get_transaction_recognition_context(
        "selected", "owner",
    )
    assert [item["transactionId"] for item in result["matches"]] == ["d", "c", "b"]
    assert result["matchingRecordCount"] == 5
    assert result["matchesTruncated"] is True
    assert result["matches"][0]["amount"] == "42.1234"
    assert result["maskedCard"] == "**** 1111"
    assert result["queryComplete"] is True
    assert result["historyCoverage"] == "INSUFFICIENT_HISTORY"
    assert result["persistedInSupportCase"] is False
    with recognition_sessions() as session:
        after = {table.name: session.exec(select(func.count()).select_from(table)).one()
                 for table in SQLModel.metadata.sorted_tables}
    assert after == before


@pytest.mark.parametrize(("days", "overrides"), [
    (0, {}), (1, {}), (-181, {}),
    (-1, {"transaction_date": SELECTED_DATE - timedelta(days=180, seconds=1)}),
    (-1, {"merchant_name": "Cafe Extra"}), (-1, {"merchant_name": None}),
    (-1, {"merchant_name": "   "}), (-1, {"amount": Decimal("42.1235")}),
    (-1, {"currency": "EUR"}), (-1, {"transaction_type": "Payment"}),
    (-1, {"transaction_status": "Declined"}), (-1, {"transaction_type": None}),
    (-1, {"product_id": "other-card"}), (-1, {"customer_id": "foreign"}),
])
def test_noncomparable_records_are_excluded(
    recognition_sessions: Callable[[], Session], days: int, overrides: dict[str, Any],
) -> None:
    with recognition_sessions() as session:
        session.add(_record("candidate", days, **overrides))
        session.commit()
    result = TransactionService(recognition_sessions).get_transaction_recognition_context(
        "selected", "owner",
    )
    assert result["matches"] == []
    assert result["matchingRecordCount"] == 0
    assert result["historyCoverage"] == "INSUFFICIENT_HISTORY"


def test_selected_and_candidate_merchants_use_the_same_normalization(
    recognition_sessions: Callable[[], Session],
) -> None:
    with recognition_sessions() as session:
        selected = session.exec(select(TransactionRecord)).one()
        selected.merchant_name = "  cAfE  "
        session.add(selected)
        session.add(_record("candidate", -1, merchant_name="Cafe"))
        session.commit()
    result = TransactionService(recognition_sessions).get_transaction_recognition_context(
        "selected", "owner",
    )
    assert [item["transactionId"] for item in result["matches"]] == ["candidate"]


def test_lower_boundary_is_inclusive_and_missing_fields_are_reported(
    recognition_sessions: Callable[[], Session],
) -> None:
    with recognition_sessions() as session:
        session.add_all([_record("boundary", -180), _record("missing", -1, merchant_name=None)])
        session.commit()
    result = TransactionService(recognition_sessions).get_transaction_recognition_context(
        "selected", "owner",
    )
    assert [item["transactionId"] for item in result["matches"]] == ["boundary"]
    assert result["missingComparisonFieldCount"] == 1


@pytest.mark.parametrize(("transaction_id", "customer_id", "product_id"), [
    ("missing", "owner", None), ("selected", "foreign", None),
    ("selected", "owner", "foreign-card"), ("selected", "owner", "bank"),
])
def test_selected_transaction_and_product_must_both_be_owned_cards(
    recognition_sessions: Callable[[], Session], transaction_id: str,
    customer_id: str, product_id: str | None,
) -> None:
    if product_id:
        with recognition_sessions() as session:
            record = session.exec(select(TransactionRecord)).one()
            record.product_id = product_id
            session.add(record)
            session.commit()
    with pytest.raises(PermissionError, match="unavailable"):
        TransactionService(recognition_sessions).get_transaction_recognition_context(
            transaction_id, customer_id,
        )


@pytest.mark.parametrize("overrides", [
    {"merchant_name": None}, {"merchant_name": " "}, {"transaction_type": "Payment"},
    {"transaction_status": "Declined"},
])
def test_missing_selected_comparison_fields_do_not_invent_matches(
    recognition_sessions: Callable[[], Session], overrides: dict[str, Any],
) -> None:
    with recognition_sessions() as session:
        selected = session.exec(select(TransactionRecord)).one()
        for key, value in overrides.items():
            setattr(selected, key, value)
        session.add(selected)
        session.commit()
    result = TransactionService(recognition_sessions).get_transaction_recognition_context(
        "selected", "owner",
    )
    assert result["matches"] == []
    assert result["coverageReason"] == "SELECTED_COMPARISON_FIELDS_UNAVAILABLE"
