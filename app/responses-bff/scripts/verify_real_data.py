"""Retired BFF database verifier; pure expectation helpers remain for regression tests."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from banking_shared.models import Customer, Product, TransactionRecord
from banking_shared.product_types import (
    ACCOUNT_PRODUCT_TYPES,
    CARD_PRODUCT_TYPES,
    card_type as shared_card_type,
    normalize_product_type,
)


@dataclass
class Evidence:
    checks: dict[str, bool]
    counts: dict[str, int]

    def equal(self, name: str, actual: object, expected: object) -> None:
        self.checks[name] = self.checks.get(name, True) and actual == expected

    def denied(self, name: str, action: Callable[[], object]) -> None:
        try:
            action()
        except PermissionError:
            self.equal(name, True, True)
        else:
            self.equal(name, False, True)


def iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def card_type(product: Product) -> str:
    return shared_card_type(product.product_type)


def masked_card_number(product: Product) -> str | None:
    return (f"**** {product.product_number[-4:]}"
            if product.product_number and len(product.product_number) > 4 else None)


def fields_equal(actual: Any, expected: dict[str, object]) -> bool:
    return all(getattr(actual, field) == value for field, value in expected.items())


def account_expected(product: Product, customer: Customer) -> dict[str, object]:
        return {"accountNumber": product.product_number.strip()
            if product.product_number and product.product_number.strip() else None,
            "userName": customer.email,
            "accountHolderFullName": " ".join(filter(None, (customer.first_name,
                                                           customer.last_name))),
            "currency": product.currency, "activationDate": iso(product.opening_date),
            "balance": format(product.current_balance, "f")
            if product.current_balance is not None else None}


def card_expected(product: Product) -> dict[str, object]:
    return {"type": card_type(product), "name": normalize_product_type(product.product_type),
            "activationDate": iso(product.opening_date),
            "expirationDate": iso(product.expiration_date), "status": product.product_status,
            "balance": float(product.current_balance)
            if product.current_balance is not None else None,
            "limit": float(product.credit_limit) if product.credit_limit is not None else None,
            "circuit": None, "number": masked_card_number(product), "cvv": None,
            "rechargedAmount": None}


def transaction_expected(record: TransactionRecord, product: Product) -> dict[str, object]:
    return {"id": record.transaction_id, "type": record.transaction_type,
            "recipientName": record.merchant_name,
            "product_number": masked_card_number(product)
            if product.product_type in CARD_PRODUCT_TYPES else product.product_number,
            "paymentType": record.channel, "amount": float(record.amount),
            "timestamp": iso(record.transaction_date), "category": record.transaction_category,
            "status": record.transaction_status,
            "description": None, "flowType": None, "recipientBankReference": None}


def compare_transactions(evidence: Evidence, name: str, actual: list[Any],
                         expected: list[TransactionRecord], product: Product) -> None:
    evidence.equal(name, len(actual) == len(expected) and all(
        fields_equal(item, transaction_expected(record, product))
        for item, record in zip(actual, expected)
    ), True)
    evidence.equal("transaction_amounts_exact", all(
        Decimal(str(item.amount)) == record.amount
        for item, record in zip(actual, expected)
    ), True)


def verify_filters(evidence: Evidence, service: Any, product: Product, customer_id: str,
                   rows: list[TransactionRecord]) -> None:
    compare_transactions(evidence, "transaction_latest", service.get_transactions(
        product.product_number, customer_id), rows[:5], product)
    compare_transactions(evidence, "transaction_unfiltered", service.get_transactions_by_type(
        product.product_number, customer_id), rows, product)
    for field, argument in (("transaction_type", "transaction_type"), ("channel", "payment_type")):
        for value in {getattr(row, field) for row in rows} - {None, ""}:
            compare_transactions(evidence, f"transaction_{argument}",
                                 service.get_transactions_by_type(product.product_number, customer_id,
                                                                  **{argument: value}),
                                 [row for row in rows if getattr(row, field) == value], product)
            evidence.counts["filter_queries"] += 1
    compare_transactions(evidence, "transaction_empty_filter", service.get_transactions_by_type(
        product.product_number, customer_id, transaction_type=str(uuid4())), [], product)
    merchant = next((row.merchant_name for row in rows if row.merchant_name), None)
    fragment = re.search(r"[A-Za-z0-9]+", merchant or "")
    if fragment:
        name = fragment.group()
        compare_transactions(evidence, "transaction_recipient",
                             service.get_transactions_by_recipient_name(
                                 product.product_number, name, customer_id),
                             [row for row in rows if name.lower() in
                              (row.merchant_name or "").lower()], product)
    compare_transactions(evidence, "transaction_empty_recipient",
                         service.get_transactions_by_recipient_name(
                             product.product_number, str(uuid4()), customer_id), [], product)


def main() -> int:
    print(json.dumps({"passed": False, "code": "LEGACY_BFF_VERIFIER_RETIRED",
                      "detail": "Use separately authorized Identity and direct REST parity checks; this script no longer verifies the database-free BFF."}))
    return 2


if __name__ == "__main__":
    try:
        exit_code = main()
    except Exception as error:
        print(json.dumps({"passed": False, "error_class": type(error).__name__}))
        exit_code = 2
    sys.exit(exit_code)