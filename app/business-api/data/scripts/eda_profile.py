from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from shared import (
    DEFAULT_END_DATE,
    DEFAULT_START_DATE,
    DIMENSION_FILES,
    parse_customer_ids,
    transaction_files,
)


@dataclass
class ColumnProfile:
    total: int = 0
    nulls: int = 0
    distinct_sample: Counter[str] = field(default_factory=Counter)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile CSV quality without loading full data in memory")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", type=date.fromisoformat, default=DEFAULT_END_DATE)
    parser.add_argument("--max-distinct-sample", type=int, default=100)
    parser.add_argument("--customer-ids")
    return parser.parse_args()


def _open_reader(path: Path) -> csv.DictReader[str]:
    return csv.DictReader(path.open("r", encoding="utf-8-sig", newline=""))


def _record_value(profile: ColumnProfile, value: str | None, max_distinct_sample: int) -> None:
    profile.total += 1
    normalized = (value or "").strip()
    if not normalized:
        profile.nulls += 1
    elif len(profile.distinct_sample) < max_distinct_sample:
        profile.distinct_sample[normalized] += 1


def _is_selected_customer(row: dict[str, str], customer_ids: set[str] | None) -> bool:
    if customer_ids is None:
        return True
    return (row.get("customer_id") or "").strip() in customer_ids


def _record_primary_id(
    row: dict[str, str],
    primary_id: str | None,
    seen_ids: set[str],
) -> bool:
    if primary_id is None:
        return False

    row_id = (row.get(primary_id) or "").strip()
    if not row_id:
        return False
    if row_id in seen_ids:
        return True

    seen_ids.add(row_id)
    return False


def _serialize_columns(column_profiles: dict[str, ColumnProfile]) -> dict[str, object]:
    columns: dict[str, object] = {}
    for name, stats in column_profiles.items():
        null_rate = stats.nulls / stats.total if stats.total else 0.0
        columns[name] = {
            "total": stats.total,
            "nulls": stats.nulls,
            "null_rate": round(null_rate, 6),
            "top_values": [
                {"value": value, "count": count}
                for value, count in stats.distinct_sample.most_common(10)
            ],
        }
    return columns


def profile_file(
    path: Path,
    max_distinct_sample: int,
    customer_ids: set[str] | None = None,
) -> dict[str, object]:
    row_count = 0
    duplicate_key_count = 0
    seen_ids: set[str] = set()
    column_profiles: dict[str, ColumnProfile] = {}

    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = reader.fieldnames or []
        for column in fieldnames:
            column_profiles[column] = ColumnProfile()

        id_candidates = [c for c in fieldnames if c.endswith("_id")]
        primary_id = id_candidates[0] if id_candidates else None

        for row in reader:
            if not _is_selected_customer(row, customer_ids):
                continue
            row_count += 1
            if _record_primary_id(row, primary_id, seen_ids):
                duplicate_key_count += 1

            for column, value in row.items():
                _record_value(column_profiles[column], value, max_distinct_sample)

    return {
        "path": str(path),
        "row_count": row_count,
        "primary_key_candidate": primary_id,
        "duplicate_key_count": duplicate_key_count,
        "columns": _serialize_columns(column_profiles),
    }


def profile_transactions(source_path: Path, start_date: date, end_date: date) -> dict[str, object]:
    files = transaction_files(source_path, start_date, end_date)
    expected_days = (end_date - start_date).days + 1
    missing_days = expected_days - len(files)
    return {
        "selected_file_count": len(files),
        "expected_day_count": expected_days,
        "missing_day_count": missing_days,
        "window": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        "sample_files": [str(path) for path in files[:5]],
    }


def build_report(
    source_path: Path,
    start_date: date,
    end_date: date,
    max_distinct_sample: int,
    customer_ids: tuple[str, ...] = (),
) -> dict[str, object]:
    customer_filter = set(customer_ids) if customer_ids else None
    table_profiles: dict[str, object] = {}
    for name in DIMENSION_FILES:
        selected_customers = customer_filter if name in {"customers.csv", "products.csv"} else None
        table_profiles[name] = profile_file(
            source_path / name,
            max_distinct_sample,
            selected_customers,
        )

    transaction_example = transaction_files(source_path, start_date, end_date)
    if transaction_example:
        table_profiles["transactions_sample"] = profile_file(
            transaction_example[0],
            max_distinct_sample,
            customer_filter,
        )

    return {
        "source_root": str(source_path),
        "customer_filter": list(customer_ids),
        "tables": table_profiles,
        "transactions_partition_health": profile_transactions(source_path, start_date, end_date),
    }


def main() -> None:
    args = parse_args()
    customer_ids = parse_customer_ids(args.customer_ids)
    report = build_report(
        args.source,
        args.start_date,
        args.end_date,
        args.max_distinct_sample,
        customer_ids,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"EDA profile created: {args.output}")


if __name__ == "__main__":
    main()
