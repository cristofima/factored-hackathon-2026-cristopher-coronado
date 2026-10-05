from __future__ import annotations

import argparse
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal

from sqlmodel import Session

from banking_data.database import create_database_engine
from banking_data.shared import parse_customer_ids
from banking_data.snapshots.snapshot_calculations import (
    CALCULATION_METHOD, INCLUDED_STATUS, DEFAULT_CREDIT_TYPES, DEFAULT_DEBIT_TYPES,
    DEFAULT_EXCLUDED_TYPES, TransactionPolicy, MonthlyMovement, SnapshotValue,
    parse_type_set, parse_month, month_start, previous_month, build_snapshot_values,
)
from banking_data.snapshots.snapshot_inputs import (
    _selected_products_statement, _selected_transactions_filter,
    load_coverage, load_observed_types, load_movements, snapshot_rows,
)
from banking_data.snapshots.snapshot_repository import upsert_snapshots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build completed monthly balances backward from products.current_balance."
    )
    parser.add_argument(
        "--credit-types",
        type=parse_type_set,
        default=DEFAULT_CREDIT_TYPES,
        help="Comma-separated credit types. Default: Deposit.",
    )
    parser.add_argument(
        "--debit-types",
        type=parse_type_set,
        default=DEFAULT_DEBIT_TYPES,
        help="Comma-separated debit types. Default: Payment,Purchase,Transfer,Withdrawal.",
    )
    parser.add_argument(
        "--excluded-types",
        type=parse_type_set,
        default=DEFAULT_EXCLUDED_TYPES,
        help="Comma-separated approved types excluded from net movement. Default: Adjustment.",
    )
    parser.add_argument("--customer-ids", help="Optional comma-separated customer IDs.")
    parser.add_argument(
        "--allow-all-customers",
        action="store_true",
        help="Required when customer-ids is omitted.",
    )
    parser.add_argument("--start-month", type=parse_month)
    parser.add_argument("--end-month", type=parse_month)
    parser.add_argument("--batch-size", type=int, default=1_000)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def batched(rows: Iterable[dict[str, object]], size: int) -> Iterable[list[dict[str, object]]]:
    batch: list[dict[str, object]] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def main() -> None:
    args = parse_args()
    customer_ids = parse_customer_ids(args.customer_ids)
    if not customer_ids and not args.allow_all_customers:
        raise SystemExit("Specify --customer-ids or explicitly pass --allow-all-customers")
    if args.batch_size < 1:
        raise SystemExit("batch-size must be greater than zero")

    policy = TransactionPolicy(args.credit_types, args.debit_types, args.excluded_types)
    with Session(create_database_engine()) as session:
        minimum_date, anchor_date = load_coverage(session, customer_ids)
        policy.validate(load_observed_types(session, customer_ids))
        start_month = args.start_month or month_start(minimum_date)
        end_month = args.end_month or previous_month(month_start(anchor_date))
        products = session.exec(_selected_products_statement(customer_ids)).all()
        if not products:
            raise SystemExit("No products exist for the selected customers")
        movements = load_movements(session, customer_ids, policy)
        rows = snapshot_rows(
            products,
            movements,
            anchor_date,
            start_month,
            end_month,
            datetime.now(timezone.utc),
            policy.description(),
        )
        row_count = 0
        excluded_count = 0
        excluded_amount = Decimal("0")
        for batch in batched(rows, args.batch_size):
            row_count += len(batch)
            excluded_count += sum(
                int(row["excluded_approved_transaction_count"]) for row in batch
            )
            excluded_amount += sum(
                (Decimal(row["excluded_approved_transaction_amount"]) for row in batch),
                start=Decimal("0"),
            )
            if not args.dry_run:
                upsert_snapshots(session, batch)
        if not args.dry_run:
            session.commit()

    mode = "validated" if args.dry_run else "upserted"
    print(
        f"Monthly snapshots {mode}: rows={row_count}, products={len(products)}, "
        f"start_month={start_month}, end_month={end_month}, anchor_date={anchor_date}, "
        f"excluded_approved_count={excluded_count}, excluded_approved_amount={excluded_amount}"
    )


if __name__ == "__main__":
    main()