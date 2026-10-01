from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

from banking_shared.product_types import normalize_product_type
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, SQLModel

DATA_DIR = Path(__file__).resolve().parents[1]
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

from database import create_database_engine
from models import Branch, Customer, Product, ServiceAgent, TransactionRecord
from inspect_sources import build_inventory
from shared import (
    DEFAULT_END_DATE,
    DEFAULT_START_DATE,
    batched,
    csv_rows,
    optional,
    parse_bool,
    parse_customer_ids,
    parse_date,
    parse_datetime,
    parse_decimal,
    transaction_files,
    partition_date,
)

Row = dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load the approved bounded banking dataset.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", type=date.fromisoformat, default=DEFAULT_END_DATE)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--customer-ids")
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


def mapped_rows(
    path: Path,
    mapper: Callable[[dict[str, str]], Row],
    customer_ids: set[str] | None = None,
) -> Iterator[Row]:
    for row in csv_rows(path):
        if customer_ids is not None and row.get("customer_id", "").strip() not in customer_ids:
            continue
        yield mapper(row)


def validate_transaction_products(
    rows: Iterator[Row],
    valid_product_ids: set[str] | None,
) -> Iterator[Row]:
    for row in rows:
        product_id = str(row["product_id"])
        if valid_product_ids is not None and product_id not in valid_product_ids:
            raise ValueError(
                f"Transaction {row['transaction_id']} references product outside customer filter: "
                f"{product_id}"
            )
        yield row


def upsert_batches(
    session: Session,
    model: type[SQLModel],
    rows: Iterator[Row],
    batch_size: int,
) -> int:
    processed = 0
    primary_keys = [column.name for column in model.__table__.primary_key.columns]
    for batch in batched(rows, batch_size):
        for row in batch:
            statement = insert(model).values(row)
            updates = {
                column.name: getattr(statement.excluded, column.name)
                for column in model.__table__.columns
                if column.name not in primary_keys
            }
            session.exec(
                statement.on_conflict_do_update(index_elements=primary_keys, set_=updates)
            )
            processed += 1
    return processed


def main() -> None:
    args = parse_args()
    if args.batch_size < 1:
        raise ValueError("batch-size must be greater than zero")

    requested_customer_ids = parse_customer_ids(args.customer_ids)
    customer_filter = set(requested_customer_ids) if requested_customer_ids else None
    inventory = build_inventory(args.source, args.start_date, args.end_date)
    counts: dict[str, int] = {"transactions": 0}
    adjustments: dict[str, int] = {}
    day_results: list[dict[str, Any]] = []
    failed_days: list[dict[str, str]] = []
    transaction_partition_files = transaction_files(args.source, args.start_date, args.end_date)
    total_days = len(transaction_partition_files)
    engine = create_database_engine()

    with Session(engine) as session:
        try:
            branch_rows = list(mapped_rows(args.source / "branches.csv", map_branch))
            valid_branch_ids = {
                str(row["branch_id"])
                for row in branch_rows
                if row.get("branch_id")
            }
            counts["branches"] = upsert_batches(
                session, Branch, iter(branch_rows), args.batch_size
            )
            mapped_customer_rows = list(
                mapped_rows(
                    args.source / "customers.csv",
                    map_customer,
                    customer_filter,
                )
            )
            if customer_filter:
                found_customer_ids = {
                    str(row["customer_id"])
                    for row in mapped_customer_rows
                }
                missing_customer_ids = sorted(customer_filter - found_customer_ids)
                if missing_customer_ids:
                    raise ValueError(
                        "Requested customer IDs were not found: "
                        + ", ".join(missing_customer_ids)
                    )

            customer_rows, customer_adjustments = sanitize_customers_registration_branch(
                iter(mapped_customer_rows),
                valid_branch_ids,
            )
            adjustments.update(customer_adjustments)
            counts["customers"] = upsert_batches(
                session, Customer, customer_rows, args.batch_size
            )
            service_agent_rows, service_agent_adjustments = sanitize_optional_branch_fk(
                mapped_rows(args.source / "service_agents.csv", map_service_agent),
                "assigned_branch_id",
                valid_branch_ids,
                "invalid_assigned_branch_refs",
            )
            adjustments.update(service_agent_adjustments)
            counts["service_agents"] = upsert_batches(
                session,
                ServiceAgent,
                service_agent_rows,
                args.batch_size,
            )
            product_rows = list(
                mapped_rows(
                    args.source / "products.csv",
                    map_product,
                    customer_filter,
                )
            )
            valid_product_ids = (
                {str(row["product_id"]) for row in product_rows}
                if customer_filter is not None
                else None
            )
            counts["products"] = upsert_batches(
                session,
                Product,
                iter(product_rows),
                args.batch_size,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise

    for index, path in enumerate(transaction_partition_files, start=1):
        day = partition_date(path)
        with Session(engine) as session:
            try:
                transaction_rows = validate_transaction_products(
                    mapped_rows(path, map_transaction, customer_filter),
                    valid_product_ids,
                )
                sanitized_transaction_rows, transaction_adjustments = sanitize_optional_branch_fk(
                    transaction_rows,
                    "branch_id",
                    valid_branch_ids,
                    "invalid_transaction_branch_refs",
                )
                loaded_rows = upsert_batches(
                    session, TransactionRecord, sanitized_transaction_rows, args.batch_size
                )
                session.commit()
                counts["transactions"] += loaded_rows
                adjustments["invalid_transaction_branch_refs"] = (
                    adjustments.get("invalid_transaction_branch_refs", 0)
                    + transaction_adjustments["invalid_transaction_branch_refs"]
                )
                day_results.append(
                    {
                        "date": day.isoformat(),
                        "status": "loaded",
                        "rows_loaded": loaded_rows,
                        "path": str(path.relative_to(args.source)).replace("\\", "/"),
                    }
                )
                print(
                    f"OK day={day.isoformat()} rows={loaded_rows} "
                    f"progress={index}/{total_days}"
                )
            except Exception as exc:
                session.rollback()
                error = str(exc)
                day_results.append(
                    {
                        "date": day.isoformat(),
                        "status": "failed",
                        "rows_loaded": 0,
                        "path": str(path.relative_to(args.source)).replace("\\", "/"),
                        "error": error,
                    }
                )
                failed_days.append({"date": day.isoformat(), "error": error})
                print(
                    f"FAIL day={day.isoformat()} progress={index}/{total_days} "
                    f"error={error}"
                )

    loaded_days = len(day_results) - len(failed_days)
    status = "completed" if not failed_days else "completed_with_errors"
    print(
        "Summary "
        f"days_total={total_days} days_loaded={loaded_days} "
        f"days_failed={len(failed_days)} rows_loaded_total={counts['transactions']}"
    )

    manifest = {
        "status": status,
        "migration_revision": "20260928_0001",
        "customer_filter": {
            "mode": "selected_customers" if requested_customer_ids else "all_customers",
            "customer_ids": list(requested_customer_ids),
        },
        "transaction_window": inventory["transaction_window"],
        "files": inventory["files"],
        "processed_rows": counts,
        "adjustments": adjustments,
        "rejected_rows": 0,
        "days_total": total_days,
        "days_loaded": loaded_days,
        "days_failed": len(failed_days),
        "failed_days": failed_days,
        "day_results": day_results,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Scoped load completed")


if __name__ == "__main__":
    main()
