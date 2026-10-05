from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Date, case, cast, func
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

DATA_DIR = Path(__file__).resolve().parents[1]
if str(DATA_DIR) not in sys.path:
    sys.path.insert(0, str(DATA_DIR))

from database import create_database_engine
from models import Product, ProductMonthlySnapshot, TransactionRecord
from scripts.shared import parse_customer_ids

CALCULATION_METHOD = "estimated_reverse_from_current_balance_v1"
INCLUDED_STATUS = "Approved"
DEFAULT_CREDIT_TYPES = frozenset({"Deposit"})
DEFAULT_DEBIT_TYPES = frozenset({"Payment", "Purchase", "Transfer", "Withdrawal"})
DEFAULT_EXCLUDED_TYPES = frozenset({"Adjustment"})


@dataclass(frozen=True)
class TransactionPolicy:
    credit_types: frozenset[str]
    debit_types: frozenset[str]
    excluded_types: frozenset[str]

    def validate(self, observed_types: set[str]) -> None:
        overlap = self.credit_types & self.debit_types
        if overlap:
            raise ValueError(
                f"Transaction types cannot be both credit and debit: {sorted(overlap)}"
            )
        excluded_overlap = self.excluded_types & (self.credit_types | self.debit_types)
        if excluded_overlap:
            raise ValueError(
                "Transaction types cannot be both included and excluded: "
                f"{sorted(excluded_overlap)}"
            )
        classified = self.credit_types | self.debit_types | self.excluded_types
        missing = observed_types - classified
        if missing:
            raise ValueError(
                "Every approved transaction type must be classified; "
                f"missing={sorted(missing)}"
            )

    def description(self) -> str:
        def joined(values: frozenset[str]) -> str:
            return ",".join(sorted(values))

        return (
            f"status={INCLUDED_STATUS};credits={joined(self.credit_types)};"
            f"debits={joined(self.debit_types)};excluded={joined(self.excluded_types)}"
        )


@dataclass(frozen=True)
class MonthlyMovement:
    net_amount: Decimal
    transaction_count: int
    excluded_amount: Decimal = Decimal("0")
    excluded_transaction_count: int = 0


@dataclass(frozen=True)
class SnapshotValue:
    snapshot_month: date
    closing_balance: Decimal
    net_transaction_amount: Decimal
    approved_transaction_count: int
    excluded_approved_transaction_amount: Decimal
    excluded_approved_transaction_count: int
    balance_uncertainty_amount: Decimal


def parse_type_set(value: str) -> frozenset[str]:
    values = frozenset(item.strip() for item in value.split(",") if item.strip())
    if not values:
        raise argparse.ArgumentTypeError("transaction type list cannot be empty")
    return values


def parse_month(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("month must use YYYY-MM-01 format") from exc
    if parsed.day != 1:
        raise argparse.ArgumentTypeError("month must be the first day of a month")
    return parsed


def month_start(value: date) -> date:
    return value.replace(day=1)


def previous_month(value: date) -> date:
    return date(value.year - 1, 12, 1) if value.month == 1 else date(value.year, value.month - 1, 1)


def build_snapshot_values(
    anchor_balance: Decimal,
    anchor_date: date,
    movements: dict[date, MonthlyMovement],
    start_month: date,
    end_month: date,
    opening_date: date | None,
) -> list[SnapshotValue]:
    if start_month.day != 1 or end_month.day != 1:
        raise ValueError("snapshot boundaries must be first-of-month dates")
    if start_month > end_month:
        raise ValueError("start month must be on or before end month")

    anchor_month = month_start(anchor_date)
    if end_month >= anchor_month:
        raise ValueError("end month must be complete and earlier than the anchor month")

    earliest_month = max(start_month, month_start(opening_date)) if opening_date else start_month
    balance = anchor_balance
    values: list[SnapshotValue] = []
    cursor = anchor_month
    zero_movement = MonthlyMovement(Decimal("0"), 0)
    balance_uncertainty = Decimal("0")

    while cursor > earliest_month:
        cursor_movement = movements.get(cursor, zero_movement)
        balance -= cursor_movement.net_amount
        balance_uncertainty += cursor_movement.excluded_amount
        snapshot_month = previous_month(cursor)
        if snapshot_month <= end_month and snapshot_month >= earliest_month:
            movement = movements.get(snapshot_month, zero_movement)
            values.append(
                SnapshotValue(
                    snapshot_month=snapshot_month,
                    closing_balance=balance,
                    net_transaction_amount=movement.net_amount,
                    approved_transaction_count=movement.transaction_count,
                    excluded_approved_transaction_amount=movement.excluded_amount,
                    excluded_approved_transaction_count=movement.excluded_transaction_count,
                    balance_uncertainty_amount=balance_uncertainty,
                )
            )
        cursor = snapshot_month

    return list(reversed(values))


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


def _selected_products_statement(customer_ids: tuple[str, ...]):
    statement = select(Product)
    if customer_ids:
        statement = statement.where(Product.customer_id.in_(customer_ids))
    return statement.order_by(Product.product_id)


def _selected_transactions_filter(customer_ids: tuple[str, ...]):
    if customer_ids:
        return TransactionRecord.customer_id.in_(customer_ids)
    return None


def load_coverage(session: Session, customer_ids: tuple[str, ...]) -> tuple[date, date]:
    statement = select(
        func.min(TransactionRecord.process_date),
        func.max(TransactionRecord.process_date),
    )
    transaction_filter = _selected_transactions_filter(customer_ids)
    if transaction_filter is not None:
        statement = statement.where(transaction_filter)
    minimum_date, maximum_date = session.exec(statement).one()
    if minimum_date is None or maximum_date is None:
        raise ValueError("No transactions exist for the selected customers")
    return minimum_date, maximum_date


def load_observed_types(session: Session, customer_ids: tuple[str, ...]) -> set[str]:
    statement = (
        select(TransactionRecord.transaction_type)
        .where(TransactionRecord.source_kind == "source")
        .where(TransactionRecord.transaction_status == INCLUDED_STATUS)
        .distinct()
    )
    transaction_filter = _selected_transactions_filter(customer_ids)
    if transaction_filter is not None:
        statement = statement.where(transaction_filter)
    values = session.exec(statement).all()
    if any(value is None for value in values):
        raise ValueError("Approved transactions contain a null transaction type")
    return {value for value in values if value is not None}


def load_movements(
    session: Session,
    customer_ids: tuple[str, ...],
    policy: TransactionPolicy,
) -> dict[str, dict[date, MonthlyMovement]]:
    transaction_month = cast(
        func.date_trunc("month", TransactionRecord.process_date), Date
    ).label("transaction_month")
    signed_amount = case(
        (
            TransactionRecord.transaction_type.in_(policy.credit_types),
            TransactionRecord.amount,
        ),
        (
            TransactionRecord.transaction_type.in_(policy.debit_types),
            -TransactionRecord.amount,
        ),
        else_=Decimal("0"),
    )
    excluded_amount = case(
        (
            TransactionRecord.transaction_type.in_(policy.excluded_types),
            TransactionRecord.amount,
        ),
        else_=Decimal("0"),
    )
    excluded_count = case(
        (TransactionRecord.transaction_type.in_(policy.excluded_types), 1),
        else_=0,
    )
    statement = (
        select(
            TransactionRecord.product_id,
            transaction_month,
            func.sum(signed_amount).label("net_amount"),
            func.count().label("transaction_count"),
            func.sum(excluded_amount).label("excluded_amount"),
            func.sum(excluded_count).label("excluded_transaction_count"),
        )
        .where(TransactionRecord.source_kind == "source")
        .where(TransactionRecord.transaction_status == INCLUDED_STATUS)
        .group_by(TransactionRecord.product_id, transaction_month)
    )
    transaction_filter = _selected_transactions_filter(customer_ids)
    if transaction_filter is not None:
        statement = statement.where(transaction_filter)

    movements: dict[str, dict[date, MonthlyMovement]] = {}
    for (
        product_id,
        transaction_month_value,
        net_amount,
        transaction_count,
        excluded_amount_value,
        excluded_transaction_count,
    ) in session.exec(statement).all():
        movements.setdefault(product_id, {})[transaction_month_value] = MonthlyMovement(
            net_amount=net_amount,
            transaction_count=transaction_count,
            excluded_amount=excluded_amount_value,
            excluded_transaction_count=excluded_transaction_count,
        )
    return movements


def snapshot_rows(
    products: Iterable[Product],
    movements: dict[str, dict[date, MonthlyMovement]],
    anchor_date: date,
    start_month: date,
    end_month: date,
    calculated_at: datetime,
    transaction_policy: str,
) -> Iterable[dict[str, object]]:
    for product in products:
        if product.current_balance is None:
            raise ValueError(f"Product has no current balance: {product.product_id}")
        for value in build_snapshot_values(
            product.current_balance,
            anchor_date,
            movements.get(product.product_id, {}),
            start_month,
            end_month,
            product.opening_date,
        ):
            yield {
                "product_id": product.product_id,
                "snapshot_month": value.snapshot_month,
                "closing_balance": value.closing_balance,
                "currency": product.currency,
                "approved_transaction_count": value.approved_transaction_count,
                "net_transaction_amount": value.net_transaction_amount,
                "excluded_approved_transaction_count": (
                    value.excluded_approved_transaction_count
                ),
                "excluded_approved_transaction_amount": (
                    value.excluded_approved_transaction_amount
                ),
                "balance_uncertainty_amount": value.balance_uncertainty_amount,
                "anchor_balance": product.current_balance,
                "anchor_date": anchor_date,
                "calculation_method": CALCULATION_METHOD,
                "transaction_policy": transaction_policy,
                "calculated_at": calculated_at,
            }


def batched(rows: Iterable[dict[str, object]], size: int) -> Iterable[list[dict[str, object]]]:
    batch: list[dict[str, object]] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def upsert_snapshots(session: Session, rows: list[dict[str, object]]) -> None:
    statement = insert(ProductMonthlySnapshot).values(rows)
    excluded = statement.excluded
    session.exec(
        statement.on_conflict_do_update(
            index_elements=["product_id", "snapshot_month"],
            set_={
                "closing_balance": excluded.closing_balance,
                "currency": excluded.currency,
                "approved_transaction_count": excluded.approved_transaction_count,
                "net_transaction_amount": excluded.net_transaction_amount,
                "excluded_approved_transaction_count": (
                    excluded.excluded_approved_transaction_count
                ),
                "excluded_approved_transaction_amount": (
                    excluded.excluded_approved_transaction_amount
                ),
                "balance_uncertainty_amount": excluded.balance_uncertainty_amount,
                "anchor_balance": excluded.anchor_balance,
                "anchor_date": excluded.anchor_date,
                "calculation_method": excluded.calculation_method,
                "transaction_policy": excluded.transaction_policy,
                "calculated_at": excluded.calculated_at,
            },
        )
    )


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