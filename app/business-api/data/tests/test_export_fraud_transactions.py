from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

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
