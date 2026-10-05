"""Source normalization and lazy optional foreign-key sanitation."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from banking_shared.product_types import normalize_product_type
from banking_shared.customer_status import normalize_customer_status

from banking_data.models import Customer
from banking_data.shared import optional, parse_bool, parse_date, parse_datetime, parse_decimal

Row = dict[str, Any]


def map_branch(row: dict[str, str]) -> Row:
    return {
        "branch_id": row["branch_id"],
        "branch_code": optional(row["branch_code"]),
        "branch_name": optional(row["branch_name"]),
        "branch_type": optional(row["branch_type"]),
        "city": optional(row["city"]),
        "state": optional(row["state"]),
        "country": optional(row["country"]),
        "branch_status": optional(row["branch_status"]),
    }


def map_customer(row: dict[str, str]) -> Row:
    mapped = {
        "customer_id": row["customer_id"],
        "email": row["email"].strip().lower(),
        "first_name": optional(row["first_name"]),
        "last_name": optional(row["last_name"]),
        "country": optional(row["country"]),
        "detected_accent": optional(row["detected_accent"]),
        "segment": optional(row["segment"]),
        "registration_date": parse_date(row["registration_date"]),
        "registration_branch_id": optional(row["registration_branch_id"]),
        "customer_status": normalize_customer_status(row["customer_status"]),
    }
    Customer.model_validate(mapped)
    return mapped


def sanitize_customers_registration_branch(
    rows: Iterator[Row],
    valid_branch_ids: set[str],
) -> tuple[Iterator[Row], dict[str, int]]:
    stats = {"invalid_registration_branch_refs": 0}

    def _iterator() -> Iterator[Row]:
        for row in rows:
            branch_id = row.get("registration_branch_id")
            if branch_id and branch_id not in valid_branch_ids:
                row = dict(row)
                row["registration_branch_id"] = None
                stats["invalid_registration_branch_refs"] += 1
            yield row

    return _iterator(), stats


def sanitize_optional_branch_fk(
    rows: Iterator[Row],
    fk_field: str,
    valid_branch_ids: set[str],
    metric_name: str,
) -> tuple[Iterator[Row], dict[str, int]]:
    stats = {metric_name: 0}

    def _iterator() -> Iterator[Row]:
        for row in rows:
            branch_id = row.get(fk_field)
            if branch_id and branch_id not in valid_branch_ids:
                row = dict(row)
                row[fk_field] = None
                stats[metric_name] += 1
            yield row

    return _iterator(), stats


def map_product(row: dict[str, str]) -> Row:
    return {
        "product_id": row["product_id"],
        "customer_id": row["customer_id"],
        "product_type": normalize_product_type(row["product_type"]),
        "product_number": optional(row["product_number"]),
        "currency": row["currency"],
        "current_balance": parse_decimal(row["current_balance"]),
        "credit_limit": parse_decimal(row["credit_limit"]),
        "interest_rate": parse_decimal(row["interest_rate"]),
        "opening_date": parse_date(row["opening_date"]),
        "expiration_date": parse_date(row["expiration_date"]),
        "product_status": optional(row["product_status"]),
        "last_transaction_date": parse_datetime(row["last_transaction_date"]),
    }


def map_transaction(row: dict[str, str]) -> Row:
    return {
        "transaction_id": row["transaction_id"],
        "transaction_date": parse_datetime(row["transaction_date"]),
        "process_date": parse_date(row["process_date"]),
        "product_id": row["product_id"],
        "customer_id": row["customer_id"],
        "transaction_type": optional(row["transaction_type"]),
        "transaction_category": optional(row["transaction_category"]),
        "amount": parse_decimal(row["amount"]),
        "currency": row["currency"],
        "amount_usd": parse_decimal(row.get("amount_usd")),
        "channel": optional(row["channel"]),
        "branch_id": optional(row["branch_id"]),
        "merchant_name": optional(row["merchant_name"]),
        "merchant_category": optional(row["merchant_category"]),
        "transaction_country": optional(row.get("transaction_country")),
        "transaction_city": optional(row.get("transaction_city")),
        "transaction_status": optional(row["transaction_status"]),
        "response_code": optional(row.get("response_code")),
        "is_fraud": parse_bool(row.get("is_fraud")),
        "fraud_score": parse_decimal(row.get("fraud_score")),
    }
