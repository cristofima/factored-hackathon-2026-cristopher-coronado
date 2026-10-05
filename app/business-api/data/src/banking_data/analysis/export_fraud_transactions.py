"""Export complete CSV rows marked as fraud, without modifying source files.

Usage: python export_fraud_transactions.py --output fraud_2026.csv
Omit --output to write CSV to stdout. Existing output files are never overwritten.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path
from typing import TextIO

DEFAULT_SOURCE = Path(r"C:\Factored\data\transactions\year=2026")


def find_partitions(
    source: Path, start_date: date | None, end_date: date | None
) -> list[Path]:
    """Select CSVs by their inclusive year/month/day partition dates."""
    if start_date and end_date and start_date > end_date:
        raise ValueError("Start date must not be after end date")
    if not source.is_dir():
        raise ValueError(f"Source directory does not exist: {source}")
    pattern = (
        "month=*/day=*/*.csv"
        if source.name.startswith("year=")
        else "year=*/month=*/day=*/*.csv"
    )
    # Existing callers may supply an unnamed single-year directory.
    candidates = sorted(source.glob(pattern))
    if not candidates and not source.name.startswith("year="):
        candidates = sorted(source.glob("month=*/day=*/*.csv"))
    files = []
    for path in candidates:
        if start_date is not None or end_date is not None:
            try:
                partition_date = date(
                    int(path.parents[2].name.removeprefix("year=")),
                    int(path.parents[1].name.removeprefix("month=")),
                    int(path.parent.name.removeprefix("day=")),
                )
            except ValueError as exc:
                raise ValueError(f"Invalid date partition: {path}") from exc
            if start_date is not None and partition_date < start_date:
                continue
            if end_date is not None and partition_date > end_date:
                continue
        files.append(path)
    if not files:
        raise ValueError(f"No daily transaction CSV files found in selected period: {source}")
    return files


def export_fraud_transactions(
    source: Path,
    output: TextIO,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> int:
    """Stream all fraud rows from selected partitions, preserving columns and values."""
    files = find_partitions(source, start_date, end_date)

    columns: list[str] | None = None
    for path in files:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream), [])
        if "is_fraud" not in header or "transaction_id" not in header:
            raise ValueError(f"Missing transaction_id or is_fraud column: {path}")
        if columns is None:
            columns = header
        elif header != columns:
            raise ValueError(f"CSV columns differ from the first partition: {path}")

    assert columns is not None
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    matches = 0
    for path in files:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"Malformed CSV record: {path}:{reader.line_num}")
                flag = row["is_fraud"].strip().lower()
                if flag not in {"true", "false", "1", "0", ""}:
                    raise ValueError(f"Invalid is_fraud value: {path}:{reader.line_num}")
                if flag in {"true", "1"}:
                    writer.writerow(row)
                    matches += 1
    return matches


def main(argv: list[str] | None = None) -> int:
    """Run the read-only source scan and report the match count on stderr."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="Transactions root or year directory")
    parser.add_argument("--year", type=int, help="Export one year (1–9999)")
    parser.add_argument("--start-date", type=date.fromisoformat, help="Inclusive YYYY-MM-DD")
    parser.add_argument("--end-date", type=date.fromisoformat, help="Inclusive YYYY-MM-DD")
    parser.add_argument("--output", type=Path, help="New output CSV; default: stdout")
    args = parser.parse_args(argv)
    try:
        start_date, end_date = args.start_date, args.end_date
        if args.year is not None:
            if start_date is not None or end_date is not None:
                raise ValueError("Use --year or date bounds, not both")
            start_date, end_date = date(args.year, 1, 1), date(args.year, 12, 31)
        source = args.source or (
            DEFAULT_SOURCE.parent
            if start_date is not None or end_date is not None
            else DEFAULT_SOURCE
        )
        if start_date is not None and end_date is not None and start_date > end_date:
            raise ValueError("Start date must not be after end date")
        if args.output is None:
            matches = export_fraud_transactions(
                source, sys.stdout, start_date=start_date, end_date=end_date
            )
        else:
            destination = args.output.resolve()
            if destination.is_relative_to(source.resolve()):
                raise ValueError("Output must be outside the source directory")
            with destination.open("x", encoding="utf-8", newline="") as output:
                matches = export_fraud_transactions(
                    source, output, start_date=start_date, end_date=end_date
                )
    except (OSError, ValueError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Fraud records exported: {matches}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
