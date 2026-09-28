from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

DEFAULT_START_DATE = date(2025, 12, 1)
DEFAULT_END_DATE = date(2026, 5, 31)
DIMENSION_FILES = ("branches.csv", "customers.csv", "service_agents.csv", "products.csv")


def parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_decimal(value: str | None) -> Decimal | None:
    return Decimal(value) if value else None


def optional(value: str | None) -> str | None:
    return value if value else None


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_metadata(path: Path) -> tuple[list[str], int]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.reader(source)
        columns = next(reader)
        row_count = sum(1 for _ in reader)
    return columns, row_count


def partition_date(path: Path) -> date:
    parts = {part.split("=", 1)[0]: part.split("=", 1)[1] for part in path.parts if "=" in part}
    return date(int(parts["year"]), int(parts["month"]), int(parts["day"]))


def transaction_files(source_path: Path, start_date: date, end_date: date) -> list[Path]:
    files = []
    for path in (source_path / "transactions").glob("year=*/month=*/day=*/*.csv"):
        selected_date = partition_date(path)
        if start_date <= selected_date <= end_date:
            files.append(path)
    return sorted(files, key=partition_date)


def csv_rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        yield from csv.DictReader(source)


def batched(rows: Iterator[dict[str, object]], size: int) -> Iterator[list[dict[str, object]]]:
    batch: list[dict[str, object]] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch
