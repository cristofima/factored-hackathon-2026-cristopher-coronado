"""Compatible CLI for the bounded source-load coordinator."""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from sqlmodel import Session

from banking_data.database import create_database_engine
from banking_data.models import Branch, Customer, Product, TransactionRecord
from banking_data.analysis.inspect_sources import build_inventory
from banking_data.shared import DEFAULT_END_DATE, DEFAULT_START_DATE, csv_rows, transaction_files
from banking_data.ingestion.source_mapping import (
    map_branch, map_customer, map_product, map_transaction,
    sanitize_customers_registration_branch, sanitize_optional_branch_fk,
)
from banking_data.ingestion.scoped_loading import mapped_rows, validate_transaction_products, upsert_batches, run_load
from banking_data.ingestion.load_manifest import write_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load the approved bounded banking dataset.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", type=date.fromisoformat, default=DEFAULT_END_DATE)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--customer-ids")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = run_load(
        args, engine_factory=create_database_engine, session_factory=Session,
        inventory_builder=build_inventory, partition_files=transaction_files,
        row_reader=csv_rows, transaction_mapper=map_transaction,
    )
    write_manifest(args.manifest, manifest)
    print("Scoped load completed")


if __name__ == "__main__":
    main()
