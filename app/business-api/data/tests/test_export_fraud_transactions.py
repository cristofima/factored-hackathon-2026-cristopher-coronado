from __future__ import annotations

import csv
import io
from datetime import date
from pathlib import Path

import pytest

from banking_data.analysis import export_fraud_transactions as fraud_export
from banking_data.analysis.export_fraud_transactions import export_fraud_transactions, main


def write_partition(source: Path, day: str, content: str) -> None:
    partition = source / "month=01" / f"day={day}"
    partition.mkdir(parents=True)
    (partition / "transactions.csv").write_text(content, encoding="utf-8")


def test_exportPreservesCompleteRecordsAcrossPartitions(tmp_path: Path) -> None:
    write_partition(tmp_path, "01", 'transaction_id,is_fraud,merchant_name\na,True,"Shop, Inc"\nb,false,Store\n')
    write_partition(tmp_path, "02", "transaction_id,is_fraud,merchant_name\nc, TRUE ,Cafe\nd,1,Market\ne,0,Other\n")
    output = io.StringIO()

    count = export_fraud_transactions(tmp_path, output)

    rows = list(csv.DictReader(io.StringIO(output.getvalue())))
    assert count == 3
    assert [row["transaction_id"] for row in rows] == ["a", "c", "d"]
    assert rows[0]["merchant_name"] == "Shop, Inc"
    assert rows[1]["is_fraud"] == " TRUE "


def test_exportWritesHeaderWhenNoFraud(tmp_path: Path) -> None:
    write_partition(tmp_path, "01", "transaction_id,is_fraud\na,False\n")
    output = io.StringIO()

    assert export_fraud_transactions(tmp_path, output) == 0
    assert output.getvalue() == "transaction_id,is_fraud\r\n"


@pytest.mark.parametrize("content, message", [
    ("transaction_id\na\n", "Missing"),
    ("transaction_id,is_fraud\na,unknown\n", "Invalid is_fraud"),
    ("transaction_id,is_fraud\na\n", "Malformed"),
])
def test_exportRejectsInvalidInput(tmp_path: Path, content: str, message: str) -> None:
    write_partition(tmp_path, "01", content)

    with pytest.raises(ValueError, match=message):
        export_fraud_transactions(tmp_path, io.StringIO())


def test_exportRejectsDifferentHeadersBeforeWriting(tmp_path: Path) -> None:
    write_partition(tmp_path, "01", "transaction_id,is_fraud\na,true\n")
    write_partition(tmp_path, "02", "is_fraud,transaction_id\ntrue,b\n")
    output = io.StringIO()

    with pytest.raises(ValueError, match="columns differ"):
        export_fraud_transactions(tmp_path, output)
    assert output.getvalue() == ""


def test_exportRejectsMissingAndEmptySource(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        export_fraud_transactions(tmp_path / "missing", io.StringIO())
    with pytest.raises(ValueError, match="No daily"):
        export_fraud_transactions(tmp_path, io.StringIO())


def test_mainProtectsSourceAndExistingOutput(tmp_path: Path) -> None:
    source = tmp_path / "source"
    write_partition(source, "01", "transaction_id,is_fraud\na,true\n")
    existing = tmp_path / "existing.csv"
    existing.write_text("preserved", encoding="utf-8")

    assert main(["--source", str(source), "--output", str(source / "fraud.csv")]) == 1
    assert main(["--source", str(source), "--output", str(existing)]) == 1
    assert existing.read_text(encoding="utf-8") == "preserved"


def test_mainExportsToNewFile(tmp_path: Path) -> None:
    source = tmp_path / "source"
    write_partition(source, "01", "transaction_id,is_fraud\na,true\n")
    destination = tmp_path / "fraud.csv"

    assert main(["--source", str(source), "--output", str(destination)]) == 0
    with destination.open(newline="", encoding="utf-8") as stream:
        assert list(csv.DictReader(stream)) == [{"transaction_id": "a", "is_fraud": "true"}]


def write_dated_partition(source: Path, partition_date: date) -> None:
    partition = (
        source / f"year={partition_date.year}" / f"month={partition_date.month:02}"
        / f"day={partition_date.day:02}"
    )
    partition.mkdir(parents=True)
    (partition / "transactions.csv").write_text(
        f"transaction_id,is_fraud\n{partition_date.isoformat()},true\n", encoding="utf-8"
    )


@pytest.mark.parametrize("year_source", [False, True])
def test_export_filters_inclusive_cross_month_range(tmp_path: Path, year_source: bool) -> None:
    for day in [date(2025, 1, 30), date(2025, 1, 31), date(2025, 2, 1), date(2025, 2, 2)]:
        write_dated_partition(tmp_path, day)
    output = io.StringIO()
    source = tmp_path / "year=2025" if year_source else tmp_path

    count = export_fraud_transactions(
        source, output, start_date=date(2025, 1, 31), end_date=date(2025, 2, 1)
    )

    assert count == 2
    assert [row["transaction_id"] for row in csv.DictReader(io.StringIO(output.getvalue()))] == [
        "2025-01-31", "2025-02-01"
    ]


@pytest.mark.parametrize("bounds, expected", [
    (["--year", "2025"], ["2025-12-30", "2025-12-31"]),
    (["--start-date", "2025-12-31", "--end-date", "2026-01-01"],
     ["2025-12-31", "2026-01-01"]),
    (["--start-date", "2026-01-01"], ["2026-01-01", "2026-01-02"]),
    (["--end-date", "2025-12-31"], ["2025-12-30", "2025-12-31"]),
])
def test_main_selects_year_or_date_bounds(
    tmp_path: Path, bounds: list[str], expected: list[str]
) -> None:
    for day in [date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 1), date(2026, 1, 2)]:
        write_dated_partition(tmp_path / "source", day)
    destination = tmp_path / "fraud.csv"

    assert main(["--source", str(tmp_path / "source"), "--output", str(destination), *bounds]) == 0
    with destination.open(newline="", encoding="utf-8") as stream:
        assert [row["transaction_id"] for row in csv.DictReader(stream)] == expected


@pytest.mark.parametrize("bounds", [
    ["--year", "0"],
    ["--year", "10000"],
    ["--year", "2025", "--start-date", "2025-01-01"],
    ["--start-date", "2026-01-02", "--end-date", "2026-01-01"],
])
def test_main_rejects_invalid_period_before_creating_output(
    tmp_path: Path, bounds: list[str]
) -> None:
    destination = tmp_path / "fraud.csv"

    assert main(["--output", str(destination), *bounds]) == 1
    assert not destination.exists()


@pytest.mark.parametrize("bounds, expected", [
    ([], ["2026-01-01"]),
    (["--year", "2025"], ["2025-01-01"]),
    (["--start-date", "2025-01-01", "--end-date", "2026-01-01"],
     ["2025-01-01", "2026-01-01"]),
])
def test_main_preserves_default_and_discovers_years(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bounds: list[str], expected: list[str]
) -> None:
    source = tmp_path / "source"
    write_dated_partition(source, date(2025, 1, 1))
    write_dated_partition(source, date(2026, 1, 1))
    monkeypatch.setattr(fraud_export, "DEFAULT_SOURCE", source / "year=2026")
    destination = tmp_path / "fraud.csv"

    assert main(["--output", str(destination), *bounds]) == 0
    with destination.open(newline="", encoding="utf-8") as stream:
        assert [row["transaction_id"] for row in csv.DictReader(stream)] == expected


def test_export_root_without_bounds_includes_all_years(tmp_path: Path) -> None:
    write_dated_partition(tmp_path, date(2025, 1, 1))
    write_dated_partition(tmp_path, date(2026, 1, 1))

    assert export_fraud_transactions(tmp_path, io.StringIO()) == 2


def test_main_rejects_output_inside_transactions_root(tmp_path: Path) -> None:
    write_dated_partition(tmp_path, date(2025, 1, 1))
    destination = tmp_path / "fraud.csv"

    assert main(["--source", str(tmp_path), "--year", "2025", "--output", str(destination)]) == 1
    assert not destination.exists()


def test_main_rejects_invalid_calendar_date() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--start-date", "2026-02-30"])
    assert exc.value.code == 2


def test_export_rejects_empty_period(tmp_path: Path) -> None:
    write_dated_partition(tmp_path, date(2025, 1, 1))
    output = io.StringIO()

    with pytest.raises(ValueError, match="selected period"):
        export_fraud_transactions(tmp_path, output, start_date=date(2026, 1, 1))
    assert output.getvalue() == ""


def test_export_rejects_invalid_partition_date(tmp_path: Path) -> None:
    write_partition(tmp_path / "year=2026", "32", "transaction_id,is_fraud\na,true\n")

    with pytest.raises(ValueError, match="Invalid date partition"):
        export_fraud_transactions(tmp_path, io.StringIO(), start_date=date(2026, 1, 1))
