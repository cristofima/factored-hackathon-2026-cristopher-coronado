from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from banking_data.snapshots.build_monthly_snapshots import (
    CALCULATION_METHOD,
    MonthlyMovement,
    TransactionPolicy,
    build_snapshot_values,
    parse_month,
)
from banking_data.models import ProductMonthlySnapshot
from banking_data.snapshots.verify_monthly_snapshots import verify_snapshots


def test_buildSnapshotValuesReconstructsCompletedMonthsFromPartialAnchorMonth() -> None:
    movements = {
        date(2026, 4, 1): MonthlyMovement(Decimal("25.0000"), 1, Decimal("5.0000"), 1),
        date(2026, 5, 1): MonthlyMovement(Decimal("-40.0000"), 2, Decimal("7.0000"), 1),
        date(2026, 6, 1): MonthlyMovement(Decimal("10.0000"), 1, Decimal("3.0000"), 1),
    }

    snapshots = build_snapshot_values(
        anchor_balance=Decimal("100.0000"),
        anchor_date=date(2026, 6, 17),
        movements=movements,
        start_month=date(2026, 4, 1),
        end_month=date(2026, 5, 1),
        opening_date=None,
    )

    assert [snapshot.snapshot_month for snapshot in snapshots] == [
        date(2026, 4, 1),
        date(2026, 5, 1),
    ]
    assert [snapshot.closing_balance for snapshot in snapshots] == [
        Decimal("130.0000"),
        Decimal("90.0000"),
    ]
    assert snapshots[0].net_transaction_amount == Decimal("25.0000")
    assert snapshots[1].approved_transaction_count == 2
    assert snapshots[0].balance_uncertainty_amount == Decimal("10.0000")
    assert snapshots[1].balance_uncertainty_amount == Decimal("3.0000")


def test_buildSnapshotValuesDoesNotPredateProductOpeningMonth() -> None:
    snapshots = build_snapshot_values(
        anchor_balance=Decimal("100.0000"),
        anchor_date=date(2026, 6, 17),
        movements={},
        start_month=date(2026, 1, 1),
        end_month=date(2026, 5, 1),
        opening_date=date(2026, 4, 15),
    )

    assert [snapshot.snapshot_month for snapshot in snapshots] == [
        date(2026, 4, 1),
        date(2026, 5, 1),
    ]


def test_transactionPolicyRejectsUnclassifiedApprovedType() -> None:
    policy = TransactionPolicy(
        credit_types=frozenset({"Deposit"}),
        debit_types=frozenset({"Withdrawal"}),
        excluded_types=frozenset(),
    )

    with pytest.raises(ValueError, match="Adjustment"):
        policy.validate({"Deposit", "Withdrawal", "Adjustment"})


def test_transactionPolicyRejectsOverlappingClassification() -> None:
    policy = TransactionPolicy(
        credit_types=frozenset({"Adjustment"}),
        debit_types=frozenset({"Adjustment"}),
        excluded_types=frozenset(),
    )

    with pytest.raises(ValueError, match="both credit and debit"):
        policy.validate({"Adjustment"})


def test_transactionPolicyAcceptsExplicitlyExcludedType() -> None:
    policy = TransactionPolicy(
        credit_types=frozenset({"Deposit"}),
        debit_types=frozenset({"Withdrawal"}),
        excluded_types=frozenset({"Adjustment"}),
    )

    policy.validate({"Deposit", "Withdrawal", "Adjustment"})


def test_parseMonthRejectsNonFirstDay() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="first day"):
        parse_month("2026-05-31")


def test_verifySnapshotsAcceptsMatchingDerivedRow() -> None:
    transaction_policy = TransactionPolicy(
        credit_types=frozenset({"Deposit"}),
        debit_types=frozenset({"Withdrawal"}),
        excluded_types=frozenset({"Adjustment"}),
    ).description()
    expected = {
        "product_id": "P001",
        "snapshot_month": date(2026, 5, 1),
        "closing_balance": Decimal("90.0000"),
        "currency": "USD",
        "approved_transaction_count": 2,
        "net_transaction_amount": Decimal("-40.0000"),
        "excluded_approved_transaction_count": 1,
        "excluded_approved_transaction_amount": Decimal("7.0000"),
        "balance_uncertainty_amount": Decimal("3.0000"),
        "anchor_balance": Decimal("100.0000"),
        "anchor_date": date(2026, 6, 17),
        "calculation_method": CALCULATION_METHOD,
        "transaction_policy": transaction_policy,
    }
    actual = ProductMonthlySnapshot(
        **expected,
        calculated_at=datetime.now(timezone.utc),
    )

    verify_snapshots([expected], [actual])


def test_verifySnapshotsRejectsBalanceMismatch() -> None:
    transaction_policy = TransactionPolicy(
        credit_types=frozenset({"Deposit"}),
        debit_types=frozenset({"Withdrawal"}),
        excluded_types=frozenset({"Adjustment"}),
    ).description()
    expected = {
        "product_id": "P001",
        "snapshot_month": date(2026, 5, 1),
        "closing_balance": Decimal("90.0000"),
        "currency": "USD",
        "approved_transaction_count": 2,
        "net_transaction_amount": Decimal("-40.0000"),
        "excluded_approved_transaction_count": 1,
        "excluded_approved_transaction_amount": Decimal("7.0000"),
        "balance_uncertainty_amount": Decimal("3.0000"),
        "anchor_balance": Decimal("100.0000"),
        "anchor_date": date(2026, 6, 17),
        "calculation_method": CALCULATION_METHOD,
        "transaction_policy": transaction_policy,
    }
    actual = ProductMonthlySnapshot(
        **{**expected, "closing_balance": Decimal("91.0000")},
        calculated_at=datetime.now(timezone.utc),
    )

    with pytest.raises(RuntimeError, match="closing_balance"):
        verify_snapshots([expected], [actual])