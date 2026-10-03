"""DB-free regression checks for the real-data verifier's public expectations."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys

import pytest
from banking_shared.models import Customer, Product, TransactionRecord
from banking_shared.product_types import ACCOUNT_PRODUCT_TYPES, CARD_PRODUCT_TYPES

spec = importlib.util.spec_from_file_location(
    "verify_real_data", Path(__file__).resolve().parents[1] / "scripts/verify_real_data.py",
)
assert spec is not None and spec.loader is not None
verifier = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = verifier
spec.loader.exec_module(verifier)


def test_retired_verifier_fails_closed_without_database_access(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert verifier.main() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["passed"] is False
    assert result["code"] == "LEGACY_BFF_VERIFIER_RETIRED"


@pytest.mark.parametrize("label", CARD_PRODUCT_TYPES)
def test_card_expectations_use_canonical_labels_and_masked_numbers(label: str) -> None:
    product = Product(product_id="internal-card", product_number="1234567890123456",
                      customer_id="customer", product_type=label, currency="USD")

    expected = verifier.card_expected(product)

    assert expected["name"] in ("Credit Card", "Debit Card")
    assert expected["type"] == ("credit" if expected["name"] == "Credit Card" else "debit")
    assert expected["number"] == "**** 3456"
    assert "id" not in expected
    assert verifier.CARD_PRODUCT_TYPES is CARD_PRODUCT_TYPES


@pytest.mark.parametrize("label", ACCOUNT_PRODUCT_TYPES)
def test_account_expectations_use_public_number(label: str) -> None:
    product = Product(product_id="internal-account", product_number=" 1234567890 ",
                      customer_id="customer", product_type=label, currency="USD")
    customer = Customer(customer_id="customer", first_name="Test", last_name="Customer")

    expected = verifier.account_expected(product, customer)

    assert expected["accountNumber"] == "1234567890"
    assert "id" not in expected
    assert verifier.ACCOUNT_PRODUCT_TYPES is ACCOUNT_PRODUCT_TYPES


@pytest.mark.parametrize("label", ACCOUNT_PRODUCT_TYPES + CARD_PRODUCT_TYPES)
def test_transaction_expectations_preserve_internal_relationships(label: str) -> None:
    product = Product(product_id="internal-product", product_number="1234567890",
                      customer_id="customer", product_type=label, currency="USD")
    record = TransactionRecord(transaction_id="transaction", product_id=product.product_id,
                               customer_id="customer", amount=Decimal("12.34"), currency="USD",
                               transaction_date=datetime(2026, 6, 1))

    expected = verifier.transaction_expected(record, product)

    assert expected["product_number"] == (
        "**** 7890" if label in CARD_PRODUCT_TYPES else "1234567890"
    )
    assert "accountId" not in expected
    assert "cardId" not in expected
    assert record.product_id == "internal-product"


@pytest.mark.parametrize("number", [None, "", "1234"])
def test_missing_or_short_card_numbers_remain_unavailable(number: str | None) -> None:
    product = Product(product_id="internal-card", product_number=number,
                      customer_id="customer", product_type="Credit Card", currency="USD")

    assert verifier.card_expected(product)["number"] is None


def test_filter_calls_use_public_number() -> None:
    product = Product(product_id="internal-account", product_number="1234567890",
                      customer_id="customer", product_type="Savings Account", currency="USD")
    calls: list[tuple[str, str]] = []

    class TransactionServiceStub:
        def get_transactions(self, identifier: str, customer_id: str) -> list[object]:
            calls.append((identifier, customer_id))
            return []

        def get_transactions_by_type(
            self, identifier: str, customer_id: str, **filters: str,
        ) -> list[object]:
            calls.append((identifier, customer_id))
            return []

        def get_transactions_by_recipient_name(
            self, identifier: str, name: str, customer_id: str,
        ) -> list[object]:
            calls.append((identifier, customer_id))
            return []

    evidence = verifier.Evidence({}, {"filter_queries": 0})
    verifier.verify_filters(evidence, TransactionServiceStub(), product, "customer", [])

    assert calls == [("1234567890", "customer")] * 4
    assert all(evidence.checks.values())