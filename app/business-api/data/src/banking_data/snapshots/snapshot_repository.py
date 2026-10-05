"""Snapshot upserts; the caller exclusively owns the commit."""
from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session

from banking_data.models import ProductMonthlySnapshot


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
