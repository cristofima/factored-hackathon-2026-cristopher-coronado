from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from banking_data.shared import (
    DEFAULT_END_DATE,
    DEFAULT_START_DATE,
    DIMENSION_FILES,
    csv_metadata,
    file_checksum,
    partition_date,
    transaction_files,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a metadata-only source inventory.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", type=date.fromisoformat, default=DEFAULT_END_DATE)
    return parser.parse_args()


def build_inventory(source_path: Path, start_date: date, end_date: date) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for name in DIMENSION_FILES:
        path = source_path / name
        columns, row_count = csv_metadata(path)
        files.append(
            {
                "path": path.relative_to(source_path).as_posix(),
                "columns": columns,
                "row_count": row_count,
                "sha256": file_checksum(path),
            }
        )

    selected_transactions = transaction_files(source_path, start_date, end_date)
    for path in selected_transactions:
        columns, row_count = csv_metadata(path)
        files.append(
            {
                "path": path.relative_to(source_path).as_posix(),
                "partition_date": partition_date(path).isoformat(),
                "columns": columns,
                "row_count": row_count,
                "sha256": file_checksum(path),
            }
        )

    expected_days = (end_date - start_date).days + 1
    if len(selected_transactions) != expected_days:
        raise RuntimeError(
            f"Transaction window is incomplete: expected {expected_days} daily files, "
            f"found {len(selected_transactions)}"
        )

    return {
        "source_format": "csv",
        "transaction_window": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily_partitions": len(selected_transactions),
        },
        "files": files,
    }


def main() -> None:
    args = parse_args()
    inventory = build_inventory(args.source, args.start_date, args.end_date)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print(f"Inventory written: {len(inventory['files'])} files")


if __name__ == "__main__":
    main()