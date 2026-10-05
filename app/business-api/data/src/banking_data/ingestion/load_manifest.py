"""Load reporting and filesystem validation, independent of database access."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from banking_data.shared import file_checksum


@dataclass(frozen=True)
class VerificationScope:
    expected: dict[str, int]
    customer_ids: tuple[str, ...]
    loaded_days: list[date]
    start_date: date
    end_date: date
    has_day_results: bool


def validate_manifest(manifest: dict[str, Any], source: Path) -> VerificationScope:
    if manifest.get("status") not in {"completed", "completed_with_errors"} or manifest.get(
        "rejected_rows"
    ) != 0:
        raise RuntimeError("Manifest does not describe a successful zero-reject load")

    for item in manifest["files"]:
        path = source / item["path"]
        if file_checksum(path) != item["sha256"]:
            raise RuntimeError(f"Source checksum changed: {item['path']}")

    expected = manifest["processed_rows"]
    customer_filter = manifest.get("customer_filter", {})
    customer_ids = tuple(customer_filter.get("customer_ids", []))
    day_results = manifest.get("day_results", [])
    loaded_days = [
        date.fromisoformat(item["date"])
        for item in day_results
        if item.get("status") == "loaded"
    ]
    if loaded_days:
        start_date = min(loaded_days)
        end_date = max(loaded_days)
    else:
        window = manifest["transaction_window"]
        start_date = date.fromisoformat(window["start_date"])
        end_date = date.fromisoformat(window["end_date"])
    return VerificationScope(
        expected, customer_ids, loaded_days, start_date, end_date, bool(day_results),
    )


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def build_load_manifest(
    inventory: dict[str, Any], requested_customer_ids: tuple[str, ...],
    counts: dict[str, int], adjustments: dict[str, int],
    day_results: list[dict[str, Any]], failed_days: list[dict[str, str]],
) -> dict[str, Any]:
    total_days = len(day_results)
    loaded_days = total_days - len(failed_days)
    status = "completed" if not failed_days else "completed_with_errors"
    return {
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
