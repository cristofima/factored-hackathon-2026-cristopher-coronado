from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, SQLModel

from database import create_database_engine
from models import Branch, Customer, Product, ServiceAgent, TransactionRecord
from scripts.inspect_sources import build_inventory
from scripts.shared import (
    DEFAULT_END_DATE,
    DEFAULT_START_DATE,
    batched,
    csv_rows,
    optional,
    parse_date,
    parse_datetime,
    parse_decimal,
    transaction_files,
)

Row = dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load the approved bounded banking dataset.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", type=date.fromisoformat, default=DEFAULT_END_DATE)
    parser.add_argument("--batch-size", type=int, default=2_000)
    return parser.parse_args()


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
    return {
        "customer_id": row["customer_id"],
        "email": row["email"].strip().lower(),
        "first_name": optional(row["first_name"]),
        "last_name": optional(row["last_name"]),
        "country": optional(row["country"]),
        "detected_accent": optional(row["detected_accent"]),
        "segment": optional(row["segment"]),
        "registration_date": parse_date(row["registration_date"]),
        "registration_branch_id": optional(row["registration_branch_id"]),
        "customer_status": optional(row["customer_status"]),
    }


def map_service_agent(row: dict[str, str]) -> Row:
    return {
        "agent_id": row["agent_id"],
        "employee_code": optional(row["employee_code"]),
        "assigned_branch_id": optional(row["assigned_branch_id"]),
        "agent_type": optional(row["agent_type"]),
        "experience_level": optional(row["experience_level"]),
        "languages": optional(row["languages"]),
        "specialty": optional(row["specialty"]),
        "agent_status": optional(row["agent_status"]),
    }


def map_product(row: dict[str, str]) -> Row:
    return {
        "product_id": row["product_id"],
        "customer_id": row["customer_id"],
        "product_type": row["product_type"],
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
        "channel": optional(row["channel"]),
        "branch_id": optional(row["branch_id"]),
        "merchant_name": optional(row["merchant_name"]),
        "merchant_category": optional(row["merchant_category"]),
        "transaction_status": optional(row["transaction_status"]),
    }


def mapped_rows(path: Path, mapper: Callable[[dict[str, str]], Row]) -> Iterator[Row]:
    for row in csv_rows(path):
        yield mapper(row)


def upsert_batches(
    session: Session,
    model: type[SQLModel],
    rows: Iterator[Row],
    batch_size: int,
) -> int:
    processed = 0
    primary_keys = [column.name for column in model.__table__.primary_key.columns]
    for batch in batched(rows, batch_size):
        statement = insert(model).values(batch)
        updates = {
            column.name: getattr(statement.excluded, column.name)
            for column in model.__table__.columns
            if column.name not in primary_keys
        }
        session.exec(
            statement.on_conflict_do_update(index_elements=primary_keys, set_=updates)
        )
        processed += len(batch)
    return processed


def main() -> None:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("batch-size must be greater than zero")

    inventory = build_inventory(args.source, args.start_date, args.end_date)
    counts: dict[str, int] = {}
    engine = create_database_engine()
    with Session(engine) as session:
        try:
            counts["branches"] = upsert_batches(
                session, Branch, mapped_rows(args.source / "branches.csv", map_branch), args.batch_size
            )
            counts["customers"] = upsert_batches(
                session, Customer, mapped_rows(args.source / "customers.csv", map_customer), args.batch_size
            )
            counts["service_agents"] = upsert_batches(
                session,
                ServiceAgent,
                mapped_rows(args.source / "service_agents.csv", map_service_agent),
                args.batch_size,
            )
            counts["products"] = upsert_batches(
                session, Product, mapped_rows(args.source / "products.csv", map_product), args.batch_size
            )
            transaction_rows = (
                mapped
                for path in transaction_files(args.source, args.start_date, args.end_date)
                for mapped in mapped_rows(path, map_transaction)
            )
            counts["transactions"] = upsert_batches(
                session, TransactionRecord, transaction_rows, args.batch_size
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

    manifest = {
        "status": "completed",
        "migration_revision": "20260928_0001",
        "transaction_window": inventory["transaction_window"],
        "files": inventory["files"],
        "processed_rows": counts,
        "rejected_rows": 0,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Scoped load completed")


if __name__ == "__main__":
    main()
