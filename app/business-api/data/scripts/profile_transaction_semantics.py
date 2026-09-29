from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import case, func
from sqlmodel import Session, select

DATA_DIR = Path(__file__).resolve().parents[1]
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

from database import create_database_engine
from models import Product, TransactionRecord
from scripts.shared import parse_customer_ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Profile transaction signs, statuses, types, dates, and product consistency."
    )
    parser.add_argument(
        "--customer-ids",
        help="Optional comma-separated customer IDs to profile.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path. Aggregate results are always printed.",
    )
    return parser.parse_args()


def build_profile(session: Session, customer_ids: tuple[str, ...]) -> dict[str, Any]:
    transaction_filter = (
        TransactionRecord.customer_id.in_(customer_ids) if customer_ids else None
    )

    distribution_statement = (
        select(
            TransactionRecord.transaction_status,
            TransactionRecord.transaction_type,
            func.count().label("row_count"),
            func.sum(case((TransactionRecord.amount < 0, 1), else_=0)).label(
                "negative_count"
            ),
            func.sum(case((TransactionRecord.amount == 0, 1), else_=0)).label(
                "zero_count"
            ),
            func.sum(case((TransactionRecord.amount > 0, 1), else_=0)).label(
                "positive_count"
            ),
            func.min(TransactionRecord.amount).label("minimum_amount"),
            func.max(TransactionRecord.amount).label("maximum_amount"),
        )
        .group_by(
            TransactionRecord.transaction_status,
            TransactionRecord.transaction_type,
        )
        .order_by(
            TransactionRecord.transaction_status,
            TransactionRecord.transaction_type,
        )
    )
    coverage_statement = select(
        func.count().label("transaction_count"),
        func.min(TransactionRecord.process_date).label("minimum_process_date"),
        func.max(TransactionRecord.process_date).label("maximum_process_date"),
    )
    mismatch_statement = (
        select(func.count())
        .select_from(TransactionRecord)
        .join(Product, TransactionRecord.product_id == Product.product_id)
        .where(
            (TransactionRecord.customer_id != Product.customer_id)
            | (TransactionRecord.currency != Product.currency)
        )
    )
    product_statement = select(
        func.count().label("product_count"),
        func.sum(case((Product.current_balance.is_(None), 1), else_=0)).label(
            "null_current_balance_count"
        ),
        func.min(Product.last_transaction_date).label("minimum_last_transaction_date"),
        func.max(Product.last_transaction_date).label("maximum_last_transaction_date"),
    )

    if transaction_filter is not None:
        distribution_statement = distribution_statement.where(transaction_filter)
        coverage_statement = coverage_statement.where(transaction_filter)
        mismatch_statement = mismatch_statement.where(transaction_filter)
        product_statement = product_statement.where(Product.customer_id.in_(customer_ids))

    distribution = [
        {
            key: str(value) if value is not None else None
            for key, value in row._mapping.items()
        }
        for row in session.exec(distribution_statement).all()
    ]
    coverage = session.exec(coverage_statement).one()._mapping
    products = session.exec(product_statement).one()._mapping

    return {
        "customer_filter": list(customer_ids),
        "coverage": {
            key: str(value) if value is not None else None
            for key, value in coverage.items()
        },
        "products": {
            key: str(value) if value is not None else None
            for key, value in products.items()
        },
        "product_consistency_mismatch_count": session.exec(mismatch_statement).one(),
        "status_type_sign_distribution": distribution,
    }


def main() -> None:
    args = parse_args()
    customer_ids = parse_customer_ids(args.customer_ids)
    with Session(create_database_engine()) as session:
        profile = build_profile(session, customer_ids)

    rendered = json.dumps(profile, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")


if __name__ == "__main__":
    main()