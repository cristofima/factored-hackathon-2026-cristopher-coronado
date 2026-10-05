from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from banking_data.snapshots import build_monthly_snapshots
from banking_data.ingestion import load_scoped_data
from banking_data.ingestion import scoped_loading
from banking_data.ingestion import verify_load
from banking_data.models import TransactionRecord
from banking_data.snapshots.snapshot_repository import upsert_snapshots


class RecordingSession:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __enter__(self) -> RecordingSession:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def commit(self) -> None:
        self.events.append("commit")

    def rollback(self) -> None:
        self.events.append("rollback")

    def exec(self, statement: object) -> RecordingSession:
        self.events.append("execute")
        return self

    def all(self) -> list[object]:
        return [object()]


def test_load_preserves_dimension_and_independent_day_transactions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    events: list[str] = []
    days = [tmp_path / "transactions_2026-01-01.csv", tmp_path / "transactions_2026-01-02.csv"]
    args = argparse.Namespace(source=tmp_path, start_date=date(2026, 1, 1),
                              end_date=date(2026, 1, 2), batch_size=2, customer_ids=None)

    def reader(path: Path) -> Any:
        if path.name.startswith("transactions"):
            yield {"transaction_id": path.stem, "product_id": "P", "branch_id": None}

    def upsert(session: RecordingSession, model: type, rows: Any, size: int) -> int:
        if model is TransactionRecord:
            row = next(rows)
            events.append(row["transaction_id"])
            if row["transaction_id"].endswith("01"):
                raise ValueError("synthetic failed day")
            return 1
        list(rows)
        return 0

    monkeypatch.setattr(scoped_loading, "upsert_batches", upsert)
    monkeypatch.setattr(scoped_loading, "partition_date", lambda path: date.fromisoformat(path.stem[-10:]))
    manifest = scoped_loading.run_load(
        args, engine_factory=lambda: object(),
        session_factory=lambda engine: RecordingSession(events),
        inventory_builder=lambda *args: {
            "transaction_window": {"start_date": "2026-01-01", "end_date": "2026-01-02"},
            "files": [],
        },
        partition_files=lambda *args: days, row_reader=reader, transaction_mapper=lambda row: row,
    )

    assert events == ["commit", "transactions_2026-01-01", "rollback",
                      "transactions_2026-01-02", "commit"]
    assert manifest["status"] == "completed_with_errors"
    assert manifest["processed_rows"]["transactions"] == 1
    assert (manifest["days_loaded"], manifest["days_failed"]) == (1, 1)
    assert [day["rows_loaded"] for day in manifest["day_results"]] == [0, 1]


def test_load_cli_persists_coordinator_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    target = tmp_path / "nested" / "manifest.json"
    monkeypatch.setattr(load_scoped_data, "parse_args", lambda: argparse.Namespace(manifest=target))
    monkeypatch.setattr(load_scoped_data, "run_load", lambda *args, **kwargs: {"status": "completed"})

    load_scoped_data.main()

    assert json.loads(target.read_text()) == {"status": "completed"}


@pytest.mark.parametrize("bad_checksum", [False, True])
def test_manifest_failure_precedes_database_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad_checksum: bool,
) -> None:
    source = tmp_path / "input.csv"
    source.write_text("synthetic")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "status": "completed" if bad_checksum else "failed", "rejected_rows": 0,
        "files": [{"path": source.name, "sha256": "wrong"}],
    }))
    monkeypatch.setattr(verify_load, "parse_args", lambda: argparse.Namespace(
        source=tmp_path, manifest=manifest,
    ))

    def forbidden_engine() -> None:
        pytest.fail("Invalid manifest must fail before database access")

    monkeypatch.setattr(verify_load, "create_database_engine", forbidden_engine)
    with pytest.raises(RuntimeError):
        verify_load.main()


@pytest.mark.parametrize("dry_run", [False, True])
def test_snapshot_coordinator_commits_once_after_all_batches_or_never_in_dry_run(
    monkeypatch: pytest.MonkeyPatch, dry_run: bool,
) -> None:
    events: list[str] = []
    args = argparse.Namespace(customer_ids="C", allow_all_customers=False, batch_size=1,
                              dry_run=dry_run, credit_types=frozenset({"Deposit"}),
                              debit_types=frozenset({"Withdrawal"}), excluded_types=frozenset(),
                              start_month=None, end_month=None)
    monkeypatch.setattr(build_monthly_snapshots, "parse_args", lambda: args)
    monkeypatch.setattr(build_monthly_snapshots, "create_database_engine", lambda: object())
    monkeypatch.setattr(build_monthly_snapshots, "Session", lambda engine: RecordingSession(events))
    monkeypatch.setattr(build_monthly_snapshots, "load_coverage", lambda *args: (
        date(2026, 1, 1), date(2026, 3, 1),
    ))
    monkeypatch.setattr(build_monthly_snapshots, "load_observed_types", lambda *args: set())
    monkeypatch.setattr(build_monthly_snapshots, "load_movements", lambda *args: {})
    monkeypatch.setattr(build_monthly_snapshots, "snapshot_rows", lambda *args: iter([
        {"excluded_approved_transaction_count": 0, "excluded_approved_transaction_amount": 0},
        {"excluded_approved_transaction_count": 0, "excluded_approved_transaction_amount": 0},
    ]))
    monkeypatch.setattr(build_monthly_snapshots, "upsert_snapshots",
                        lambda *args: events.append("upsert"))

    build_monthly_snapshots.main()

    assert events == (["execute"] if dry_run else ["execute", "upsert", "upsert", "commit"])


def test_snapshot_repository_never_commits() -> None:
    events: list[str] = []

    upsert_snapshots(RecordingSession(events), [{"product_id": "P", "snapshot_month": date(2026, 1, 1)}])

    assert events == ["execute"]
