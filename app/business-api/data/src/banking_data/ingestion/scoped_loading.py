from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, SQLModel

from banking_data.ingestion.load_manifest import build_load_manifest
from banking_data.models import Branch, Customer, Product, TransactionRecord
from banking_data.shared import batched, csv_rows, parse_customer_ids, partition_date
from banking_data.ingestion.source_mapping import (
    map_branch,
    map_customer,
    map_product,
    sanitize_customers_registration_branch,
    sanitize_optional_branch_fk,
)

Row = dict[str, Any]


def mapped_rows(
    path: Path,
    mapper: Callable[[dict[str, str]], Row],
    customer_ids: set[str] | None = None,
    *, row_reader: Callable[[Path], Iterator[dict[str, str]]] = csv_rows,
) -> Iterator[Row]:
    for row in row_reader(path):
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
            if model is TransactionRecord:
                existing = session.get(TransactionRecord, row["transaction_id"])
                if existing is not None and existing.source_kind != "source":
                    raise ValueError("Source ingestion cannot overwrite a runtime movement")
            statement = insert(model).values(row)
            updates = {
                column.name: getattr(statement.excluded, column.name)
                for column in model.__table__.columns
                if column.name not in primary_keys
            }
            session.exec(
                statement.on_conflict_do_update(
                    index_elements=primary_keys, set_=updates,
                    where=model.source_kind == "source" if model is TransactionRecord else None,
                )
            )
            processed += 1
    return processed


def run_load(
    args: argparse.Namespace,
    *, engine_factory: Callable[..., Any], session_factory: Callable[..., Any],
    inventory_builder: Callable[..., Any], partition_files: Callable[..., Any],
    row_reader: Callable[..., Any], transaction_mapper: Callable[..., Any],
) -> dict[str, Any]:
    if args.batch_size < 1:
        raise ValueError("batch-size must be greater than zero")

    requested_customer_ids = parse_customer_ids(args.customer_ids)
    customer_filter = set(requested_customer_ids) if requested_customer_ids else None
    inventory = inventory_builder(args.source, args.start_date, args.end_date)
    counts: dict[str, int] = {"transactions": 0}
    adjustments: dict[str, int] = {}
    day_results: list[dict[str, Any]] = []
    failed_days: list[dict[str, str]] = []
    transaction_partition_files = partition_files(args.source, args.start_date, args.end_date)
    total_days = len(transaction_partition_files)
    engine = engine_factory()

    with session_factory(engine) as session:
        try:
            branch_rows = list(mapped_rows(args.source / "branches.csv", map_branch, row_reader=row_reader))
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
                    row_reader=row_reader,
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
            product_rows = list(
                mapped_rows(
                    args.source / "products.csv",
                    map_product,
                    customer_filter,
                    row_reader=row_reader,
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
        with session_factory(engine) as session:
            try:
                transaction_rows = validate_transaction_products(
                    mapped_rows(path, transaction_mapper, customer_filter, row_reader=row_reader),
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
    print(
        "Summary "
        f"days_total={total_days} days_loaded={loaded_days} "
        f"days_failed={len(failed_days)} rows_loaded_total={counts['transactions']}"
    )

    return build_load_manifest(
        inventory, requested_customer_ids, counts, adjustments, day_results, failed_days,
    )
