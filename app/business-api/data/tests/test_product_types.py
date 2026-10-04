from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from banking_shared.product_types import (
    ACCOUNT_PRODUCT_TYPES,
    CARD_PRODUCT_TYPES,
    normalize_product_type,
)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from scripts import load_scoped_data
from scripts.load_scoped_data import map_product


PRODUCT_TYPES = (
    ("Cuenta Ahorro", "Savings Account"),
    ("Cuenta Corriente", "Checking Account"),
    ("Inversi\u00f3n", "Investment"),
    ("Pr\u00e9stamo Hipotecario", "Mortgage Loan"),
    ("Pr\u00e9stamo Personal", "Personal Loan"),
    ("Seguro", "Insurance"),
    ("Tarjeta Cr\u00e9dito", "Credit Card"),
    ("Tarjeta D\u00e9bito", "Debit Card"),
)


@pytest.mark.parametrize(("legacy", "canonical"), PRODUCT_TYPES)
def test_normalization_and_ingestion(legacy: str, canonical: str) -> None:
    for label in (legacy, canonical, legacy.upper(), canonical.lower()):
        value = f"  {label}  "
        assert normalize_product_type(value) == canonical
        row = dict.fromkeys((
            "product_id", "customer_id", "product_number", "currency", "current_balance",
            "credit_limit", "interest_rate", "opening_date", "expiration_date",
            "product_status", "last_transaction_date",
        ), "")
        row["product_type"] = value
        assert map_product(row)["product_type"] == canonical


@pytest.mark.parametrize("value", ("", "  ", "Tarjeta", "Unknown", "Savings"))
def test_unknown_product_type_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="Unknown product_type"):
        normalize_product_type(value)
    with pytest.raises(ValueError, match="Unknown product_type"):
        map_product({"product_id": "P1", "customer_id": "C1", "product_type": value})


@pytest.mark.parametrize(("value", "expected"), (
    ("inversion", "Investment"),
    ("prestamo hipotecario", "Mortgage Loan"),
    ("prestamo personal", "Personal Loan"),
    ("Pr\u00e9stamo Persona", "Personal Loan"),
    ("tarjeta credito", "Credit Card"),
    ("tarjeta debito", "Debit Card"),
    ("Tarjeta Cre\u0301dito", "Credit Card"),
))
def test_accent_normalization(value: str, expected: str) -> None:
    assert normalize_product_type(value) == expected


def test_category_query_values_include_only_canonical_english() -> None:
    assert ACCOUNT_PRODUCT_TYPES == ("Savings Account", "Checking Account")
    assert CARD_PRODUCT_TYPES == ("Credit Card", "Debit Card")


@pytest.fixture
def loader_rows() -> dict[str, list[dict[str, str]]]:
    branch = dict.fromkeys((
        "branch_id", "branch_code", "branch_name", "branch_type", "city", "state",
        "country", "branch_status",
    ), "")
    branch["branch_id"] = "B1"
    customer = dict.fromkeys((
        "customer_id", "email", "first_name", "last_name", "country", "detected_accent",
        "segment", "registration_date", "registration_branch_id", "customer_status",
    ), "")
    product = dict.fromkeys((
        "product_id", "customer_id", "product_number", "currency", "current_balance",
        "credit_limit", "interest_rate", "opening_date", "expiration_date",
        "product_status", "last_transaction_date",
    ), "")
    transaction = dict.fromkeys((
        "transaction_id", "transaction_date", "process_date", "product_id", "customer_id",
        "transaction_type", "transaction_category", "amount", "currency", "channel",
        "branch_id", "merchant_name", "merchant_category", "transaction_status",
    ), "")
    return {
        "branches.csv": [branch],
        "customers.csv": [{**customer, "customer_id": "C1"}, {**customer, "customer_id": "C2"}],
        "products.csv": [
            {**product, "product_id": "P1", "customer_id": "C1", "product_type": "Cuenta Ahorro"},
            {**product, "product_id": "P2", "customer_id": "C2", "product_type": "Unknown"},
        ],
        "daily.csv": [
            {**transaction, "transaction_id": "T1", "product_id": "P1", "customer_id": "C1"},
            {**transaction, "transaction_id": "T2", "product_id": "P2", "customer_id": "C2"},
        ],
    }


@pytest.mark.parametrize("unknown_is_scoped", (True, False))
def test_loader_unknown_product_type_respects_customer_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    loader_rows: dict[str, list[dict[str, str]]],
    unknown_is_scoped: bool,
) -> None:
    source = tmp_path / "source"
    manifest = tmp_path / "manifests" / "load.json"
    selected_day = date(2026, 3, 1)
    partition = source / "transactions" / "year=2026" / "month=03" / "day=01" / "daily.csv"
    args = argparse.Namespace(
        source=source, manifest=manifest, start_date=selected_day, end_date=selected_day,
        batch_size=1, customer_ids="C1,C2" if unknown_is_scoped else "C1",
    )
    session = MagicMock()
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = session
    transaction_mapper = MagicMock(wraps=load_scoped_data.map_transaction)
    monkeypatch.setattr(load_scoped_data, "parse_args", lambda: args)
    monkeypatch.setattr(load_scoped_data, "create_database_engine", MagicMock())
    monkeypatch.setattr(load_scoped_data, "Session", session_factory)
    monkeypatch.setattr(load_scoped_data, "build_inventory", lambda *args: {
        "transaction_window": {}, "files": [],
    })
    monkeypatch.setattr(load_scoped_data, "transaction_files", lambda *args: [partition])
    monkeypatch.setattr(load_scoped_data, "csv_rows", lambda path: iter(loader_rows[path.name]))
    monkeypatch.setattr(load_scoped_data, "map_transaction", transaction_mapper)

    if unknown_is_scoped:
        with pytest.raises(ValueError, match="Unknown product_type.*Unknown"):
            load_scoped_data.main()

        session.rollback.assert_called_once_with()
        session.commit.assert_not_called()
        assert session_factory.call_count == 1
        transaction_mapper.assert_not_called()
        assert not manifest.exists()
        assert [call.args[0].table.name for call in session.exec.call_args_list] == [
            load_scoped_data.Branch.__tablename__,
            load_scoped_data.Customer.__tablename__,
            load_scoped_data.Customer.__tablename__,
        ]
    else:
        load_scoped_data.main()

        session.rollback.assert_not_called()
        assert session.commit.call_count == 2
        assert session_factory.call_count == 2
        transaction_mapper.assert_called_once_with(loader_rows["daily.csv"][0])
        loaded_manifest = json.loads(manifest.read_text(encoding="utf-8"))
        assert loaded_manifest["status"] == "completed"
        assert loaded_manifest["customer_filter"]["customer_ids"] == ["C1"]
        assert loaded_manifest["processed_rows"] == {
            "branches": 1, "customers": 1, "products": 1, "transactions": 1,
        }
        assert loaded_manifest["days_loaded"] == 1
        assert loaded_manifest["days_failed"] == 0