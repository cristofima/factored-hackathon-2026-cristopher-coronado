"""Export complete CSV rows marked as fraud, without modifying source files.

Usage: python export_fraud_transactions.py --output fraud_2026.csv
Omit --output to write CSV to stdout. Existing output files are never overwritten.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import TextIO

DEFAULT_SOURCE = Path(r"C:\Factored\data\transactions\year=2026")


def export_fraud_transactions(source: Path, output: TextIO) -> int:
    """Stream all fraud rows from daily partitions, preserving columns and values."""
    if not source.is_dir():
        raise ValueError(f"Source directory does not exist: {source}")
    files = sorted(source.glob("month=*/day=*/*.csv"))
    if not files:
        raise ValueError(f"No daily transaction CSV files found in {source}")

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
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, help="New output CSV; default: stdout")
    args = parser.parse_args(argv)
    try:
        if args.output is None:
            matches = export_fraud_transactions(args.source, sys.stdout)
        else:
            source = args.source.resolve()
            destination = args.output.resolve()
            if destination.is_relative_to(source):
                raise ValueError("Output must be outside the source directory")
            with destination.open("x", encoding="utf-8", newline="") as output:
                matches = export_fraud_transactions(args.source, output)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Fraud records exported: {matches}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
