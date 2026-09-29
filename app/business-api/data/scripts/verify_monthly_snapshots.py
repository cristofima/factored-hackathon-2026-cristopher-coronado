from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

DATA_DIR = Path(__file__).resolve().parents[1]
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

from database import create_database_engine
from models import Product, ProductMonthlySnapshot
from scripts.build_monthly_snapshots import (
    CALCULATION_METHOD,
    DEFAULT_CREDIT_TYPES,
    DEFAULT_DEBIT_TYPES,
    DEFAULT_EXCLUDED_TYPES,
    TransactionPolicy,
    load_coverage,
    load_movements,
    load_observed_types,
    month_start,
    parse_month,
    parse_type_set,
    previous_month,
    snapshot_rows,
)
from scripts.shared import parse_customer_ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recompute and verify derived monthly product balance snapshots."
    )
    parser.add_argument("--credit-types", type=parse_type_set, default=DEFAULT_CREDIT_TYPES)
    parser.add_argument("--debit-types", type=parse_type_set, default=DEFAULT_DEBIT_TYPES)
    parser.add_argument("--excluded-types", type=parse_type_set, default=DEFAULT_EXCLUDED_TYPES)
    parser.add_argument("--customer-ids", help="Optional comma-separated customer IDs.")
    parser.add_argument(
        "--allow-all-customers",
        action="store_true",
        help="Required when customer-ids is omitted.",
    )
    parser.add_argument("--start-month", type=parse_month)
    parser.add_argument("--end-month", type=parse_month)
    return parser.parse_args()


def _products_statement(customer_ids: tuple[str, ...]):
    statement = select(Product)
    if customer_ids:
        statement = statement.where(Product.customer_id.in_(customer_ids))
    return statement.order_by(Product.product_id)


def _snapshots_statement(
    customer_ids: tuple[str, ...],
    start_month: date,
    end_month: date,
):
    statement = (
        select(ProductMonthlySnapshot)
        .join(Product, ProductMonthlySnapshot.product_id == Product.product_id)
        .where(
            ProductMonthlySnapshot.snapshot_month >= start_month,
            ProductMonthlySnapshot.snapshot_month <= end_month,
        )
    )
    if customer_ids:
        statement = statement.where(Product.customer_id.in_(customer_ids))
    return statement


def verify_snapshots(
    expected_rows: list[dict[str, object]],
    actual_rows: list[ProductMonthlySnapshot],
) -> None:
    expected = {
        (row["product_id"], row["snapshot_month"]): row for row in expected_rows
    }
    actual = {
        (row.product_id, row.snapshot_month): row for row in actual_rows
    }
    missing = sorted(expected.keys() - actual.keys())
    unexpected = sorted(actual.keys() - expected.keys())
    mismatches: list[str] = []

    for key in sorted(expected.keys() & actual.keys()):
        expected_row = expected[key]
        actual_row = actual[key]
        comparable = {
            "closing_balance": actual_row.closing_balance,
            "currency": actual_row.currency,
            "approved_transaction_count": actual_row.approved_transaction_count,
            "net_transaction_amount": actual_row.net_transaction_amount,
            "excluded_approved_transaction_count": (
                actual_row.excluded_approved_transaction_count
            ),
            "excluded_approved_transaction_amount": (
                actual_row.excluded_approved_transaction_amount
            ),
            "balance_uncertainty_amount": actual_row.balance_uncertainty_amount,
            "anchor_balance": actual_row.anchor_balance,
            "anchor_date": actual_row.anchor_date,
            "calculation_method": actual_row.calculation_method,
            "transaction_policy": actual_row.transaction_policy,
        }
        differences = {
            field: (expected_row[field], actual_value)
            for field, actual_value in comparable.items()
            if expected_row[field] != actual_value
        }
        if differences:
            mismatches.append(f"{key}: {differences}")

    if missing or unexpected or mismatches:
        raise RuntimeError(
            "Monthly snapshot verification failed: "
            f"missing={missing[:10]}, unexpected={unexpected[:10]}, "
            f"mismatches={mismatches[:10]}"
        )


def main() -> None:
    args = parse_args()
    customer_ids = parse_customer_ids(args.customer_ids)
    if not customer_ids and not args.allow_all_customers:
        raise SystemExit("Specify --customer-ids or explicitly pass --allow-all-customers")

    policy = TransactionPolicy(args.credit_types, args.debit_types, args.excluded_types)
    with Session(create_database_engine()) as session:
        minimum_date, anchor_date = load_coverage(session, customer_ids)
        policy.validate(load_observed_types(session, customer_ids))
        start_month = args.start_month or month_start(minimum_date)
        end_month = args.end_month or previous_month(month_start(anchor_date))
        products = session.exec(_products_statement(customer_ids)).all()
        movements = load_movements(session, customer_ids, policy)
        expected_rows = list(
            snapshot_rows(
                products,
                movements,
                anchor_date,
                start_month,
                end_month,
                calculated_at=datetime.now(timezone.utc),
                transaction_policy=policy.description(),
            )
        )
        actual_rows = session.exec(
            _snapshots_statement(customer_ids, start_month, end_month)
        ).all()

    verify_snapshots(expected_rows, actual_rows)
    if any(row.calculation_method != CALCULATION_METHOD for row in actual_rows):
        raise RuntimeError("Monthly snapshot verification found an unsupported calculation method")
    print(
        f"Monthly snapshot verification passed: rows={len(actual_rows)}, "
        f"products={len(products)}, start_month={start_month}, end_month={end_month}, "
        f"anchor_date={anchor_date}"
    )


if __name__ == "__main__":
    main()