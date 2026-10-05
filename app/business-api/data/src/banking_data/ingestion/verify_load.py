from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select


from banking_data.database import create_database_engine
from banking_data.models import Branch, Customer, LegacyServiceAgent, Product, TransactionRecord
from banking_data.ingestion.load_manifest import validate_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a completed scoped data load.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def scalar_count(session: Session, model: type) -> int:
    return session.exec(select(func.count()).select_from(model)).one()


def customer_count(session: Session, customer_ids: tuple[str, ...]) -> int:
    statement = select(func.count()).select_from(Customer)
    if customer_ids:
        statement = statement.where(Customer.customer_id.in_(customer_ids))
    return session.exec(statement).one()


def product_count(session: Session, customer_ids: tuple[str, ...]) -> int:
    statement = select(func.count()).select_from(Product)
    if customer_ids:
        statement = statement.where(Product.customer_id.in_(customer_ids))
    return session.exec(statement).one()


def transaction_count(
    session: Session,
    loaded_days: list[date],
    start_date: date,
    end_date: date,
    has_day_results: bool,
    customer_ids: tuple[str, ...],
) -> int:
    if has_day_results and not loaded_days:
        return 0

    statement = select(func.count()).select_from(TransactionRecord).where(TransactionRecord.source_kind == "source")
    if loaded_days:
        statement = statement.where(TransactionRecord.process_date.in_(loaded_days))
    else:
        statement = statement.where(
            TransactionRecord.process_date >= start_date,
            TransactionRecord.process_date <= end_date,
        )
    if customer_ids:
        statement = statement.where(TransactionRecord.customer_id.in_(customer_ids))
    return session.exec(statement).one()


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    scope = validate_manifest(manifest, args.source)
    expected = scope.expected
    customer_ids = scope.customer_ids
    loaded_days = scope.loaded_days
    start_date, end_date = scope.start_date, scope.end_date
    with Session(create_database_engine()) as session:
        actual = {
            "branches": scalar_count(session, Branch),
            "customers": customer_count(session, customer_ids),
            "products": product_count(session, customer_ids),
            "transactions": transaction_count(
                session,
                loaded_days,
                start_date,
                end_date,
                scope.has_day_results,
                customer_ids,
            ),
        }
        orphan_products_statement = (
            select(func.count())
            .select_from(Product)
            .outerjoin(Customer, Product.customer_id == Customer.customer_id)
            .where(Customer.customer_id.is_(None))
        )
        if customer_ids:
            orphan_products_statement = orphan_products_statement.where(
                Product.customer_id.in_(customer_ids)
            )
        orphan_products = session.exec(orphan_products_statement).one()

        orphan_transactions_statement = (
            select(func.count())
            .select_from(TransactionRecord).where(TransactionRecord.source_kind == "source")
            .outerjoin(Product, TransactionRecord.product_id == Product.product_id)
            .where(Product.product_id.is_(None))
        )
        if loaded_days:
            orphan_transactions_statement = orphan_transactions_statement.where(
                TransactionRecord.process_date.in_(loaded_days)
            )
        else:
            orphan_transactions_statement = orphan_transactions_statement.where(
                TransactionRecord.process_date >= start_date,
                TransactionRecord.process_date <= end_date,
            )
        if customer_ids:
            orphan_transactions_statement = orphan_transactions_statement.where(
                TransactionRecord.customer_id.in_(customer_ids)
            )
        orphan_transactions = session.exec(orphan_transactions_statement).one()

    if "service_agents" in expected:
        # Older manifests verify the preserved snapshot, not an active reviewer catalog.
        with Session(create_database_engine()) as session:
            actual["service_agents"] = scalar_count(session, LegacyServiceAgent)
        print("Legacy service_agents count verified against migration archive only")
    mismatches = {name: (expected[name], actual[name]) for name in expected if expected[name] != actual[name]}
    if mismatches or orphan_products or orphan_transactions:
        raise RuntimeError(
            f"Verification failed: count_mismatches={mismatches}, "
            f"orphan_products={orphan_products}, orphan_transactions={orphan_transactions}"
        )
    print("Load verification passed")


if __name__ == "__main__":
    main()
