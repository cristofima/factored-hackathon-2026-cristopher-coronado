from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

from database import create_database_engine
from models import Branch, Customer, Product, ServiceAgent, TransactionRecord
from scripts.shared import file_checksum


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a completed scoped data load.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def scalar_count(session: Session, model: type) -> int:
    return session.exec(select(func.count()).select_from(model)).one()


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("status") != "completed" or manifest.get("rejected_rows") != 0:
        raise RuntimeError("Manifest does not describe a successful zero-reject load")

    for item in manifest["files"]:
        path = args.source / item["path"]
        if file_checksum(path) != item["sha256"]:
            raise RuntimeError(f"Source checksum changed: {item['path']}")

    expected = manifest["processed_rows"]
    window = manifest["transaction_window"]
    start_date = date.fromisoformat(window["start_date"])
    end_date = date.fromisoformat(window["end_date"])
    with Session(create_database_engine()) as session:
        actual = {
            "branches": scalar_count(session, Branch),
            "customers": scalar_count(session, Customer),
            "service_agents": scalar_count(session, ServiceAgent),
            "products": scalar_count(session, Product),
            "transactions": session.exec(
                select(func.count())
                .select_from(TransactionRecord)
                .where(TransactionRecord.process_date.between(start_date, end_date))
            ).one(),
        }
        orphan_products = session.exec(
            select(func.count())
            .select_from(Product)
            .outerjoin(Customer, Product.customer_id == Customer.customer_id)
            .where(Customer.customer_id.is_(None))
        ).one()
        orphan_transactions = session.exec(
            select(func.count())
            .select_from(TransactionRecord)
            .outerjoin(Product, TransactionRecord.product_id == Product.product_id)
            .where(Product.product_id.is_(None))
        ).one()

    mismatches = {name: (expected[name], actual[name]) for name in expected if expected[name] != actual[name]}
    if mismatches or orphan_products or orphan_transactions:
        raise RuntimeError(
            f"Verification failed: count_mismatches={mismatches}, "
            f"orphan_products={orphan_products}, orphan_transactions={orphan_transactions}"
        )
    print("Load verification passed")


if __name__ == "__main__":
    main()
