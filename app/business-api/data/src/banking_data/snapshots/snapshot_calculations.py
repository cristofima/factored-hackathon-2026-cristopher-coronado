"""Pure policy validation and reverse monthly balance reconstruction."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

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
