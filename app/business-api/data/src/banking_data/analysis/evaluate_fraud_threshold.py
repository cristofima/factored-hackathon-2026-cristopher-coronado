"""Offline precision/recall evaluation of candidate fraud_score thresholds.

Scans the full raw transaction CSVs (not the loaded Postgres subset, for statistical
power) and compares each candidate fraud_score threshold against the dataset's own
is_fraud label. This is the data-backed baseline for the transaction-dispute triage
threshold; is_fraud is used here only for offline evaluation, never surfaced to the agent.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from banking_data.shared import parse_bool, transaction_files

DEFAULT_START_DATE = date(2023, 1, 1)
DEFAULT_END_DATE = date(2026, 12, 31)
DEFAULT_THRESHOLDS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


@dataclass
class ScoreStats:
    count: int = 0
    total: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    samples: list[float] | None = None

    def update(self, score: float, keep_sample: bool) -> None:
        self.count += 1
        self.total += score
        self.minimum = score if self.minimum is None else min(self.minimum, score)
        self.maximum = score if self.maximum is None else max(self.maximum, score)
        if keep_sample:
            if self.samples is None:
                self.samples = []
            self.samples.append(score)

    def as_summary(self) -> dict[str, object]:
        mean = self.total / self.count if self.count else None
        percentiles: dict[str, float | None] = {}
        if self.samples:
            ordered = sorted(self.samples)
            for p in (50, 75, 90, 95, 99):
                index = min(len(ordered) - 1, int(len(ordered) * p / 100))
                percentiles[f"p{p}"] = round(ordered[index], 4)
        return {
            "count": self.count,
            "mean": round(mean, 4) if mean is not None else None,
            "min": self.minimum,
            "max": self.maximum,
            "percentiles_from_sample": percentiles,
            "sample_size": len(self.samples) if self.samples else 0,
        }


@dataclass
class ThresholdCounts:
    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0

    def update(self, predicted_fraud: bool, actual_fraud: bool) -> None:
        if predicted_fraud and actual_fraud:
            self.true_positive += 1
        elif predicted_fraud and not actual_fraud:
            self.false_positive += 1
        elif not predicted_fraud and actual_fraud:
            self.false_negative += 1
        else:
            self.true_negative += 1

    def as_metrics(self) -> dict[str, object]:
        predicted_positive = self.true_positive + self.false_positive
        actual_positive = self.true_positive + self.false_negative
        precision = self.true_positive / predicted_positive if predicted_positive else None
        recall = self.true_positive / actual_positive if actual_positive else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and (precision + recall) > 0
            else None
        )
        return {
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "true_negative": self.true_negative,
            "false_negative": self.false_negative,
            "precision": round(precision, 6) if precision is not None else None,
            "recall": round(recall, 6) if recall is not None else None,
            "f1": round(f1, 6) if f1 is not None else None,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate candidate fraud_score thresholds against the dataset's is_fraud label."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, default=DEFAULT_START_DATE)
    parser.add_argument("--end-date", type=date.fromisoformat, default=DEFAULT_END_DATE)
    parser.add_argument(
        "--thresholds",
        default=",".join(str(value) for value in DEFAULT_THRESHOLDS),
        help="Comma-separated candidate thresholds, in the same scale as fraud_score.",
    )
    parser.add_argument(
        "--describe",
        action="store_true",
        help="Print fraud_score min/mean/max/percentiles split by is_fraud instead of running the threshold sweep.",
    )
    parser.add_argument(
        "--sample-every",
        type=int,
        default=50,
        help="Keep 1-in-N rows per label for percentile estimation in --describe mode.",
    )
    return parser.parse_args()


def parse_thresholds(value: str) -> tuple[float, ...]:
    thresholds = tuple(sorted({float(item.strip()) for item in value.split(",") if item.strip()}))
    if not thresholds:
        raise ValueError("thresholds must contain at least one value")
    return thresholds


def _score_row(
    row: dict[str, str],
    thresholds: tuple[float, ...],
    counts: dict[float, ThresholdCounts],
) -> tuple[bool, bool]:
    """Returns (was_labeled, had_missing_score) for one row."""
    is_fraud = parse_bool(row.get("is_fraud"))
    if is_fraud is None:
        return False, False

    score_text = (row.get("fraud_score") or "").strip()
    if not score_text:
        return True, True

    score = float(score_text)
    for threshold in thresholds:
        counts[threshold].update(score >= threshold, is_fraud)
    return True, False


def evaluate(
    files: list[Path],
    thresholds: tuple[float, ...],
) -> dict[str, object]:
    counts = {threshold: ThresholdCounts() for threshold in thresholds}
    total_rows = 0
    labeled_rows = 0
    fraud_rows = 0
    missing_score_rows = 0

    for path in files:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                total_rows += 1
                was_labeled, missing_score = _score_row(row, thresholds, counts)
                if was_labeled:
                    labeled_rows += 1
                    if parse_bool(row.get("is_fraud")):
                        fraud_rows += 1
                if missing_score:
                    missing_score_rows += 1

    return {
        "file_count": len(files),
        "total_rows": total_rows,
        "labeled_rows": labeled_rows,
        "fraud_rows": fraud_rows,
        "missing_score_rows": missing_score_rows,
        "thresholds": {
            str(threshold): counts[threshold].as_metrics() for threshold in thresholds
        },
    }


def describe(files: list[Path], sample_every: int) -> dict[str, object]:
    stats = {True: ScoreStats(), False: ScoreStats()}
    row_index = 0
    for path in files:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                is_fraud = parse_bool(row.get("is_fraud"))
                if is_fraud is None:
                    continue
                score_text = (row.get("fraud_score") or "").strip()
                if not score_text:
                    continue
                row_index += 1
                stats[is_fraud].update(float(score_text), row_index % sample_every == 0)
    return {
        "fraud_rows": stats[True].as_summary(),
        "non_fraud_rows": stats[False].as_summary(),
    }


def main() -> None:
    args = parse_args()
    files = transaction_files(args.source, args.start_date, args.end_date)
    if not files:
        raise SystemExit(f"No transaction files found under {args.source} for the requested window")

    if args.describe:
        result: dict[str, object] = describe(files, args.sample_every)
    else:
        thresholds = parse_thresholds(args.thresholds)
        result = evaluate(files, thresholds)

    result["window"] = {
        "start_date": args.start_date.isoformat(),
        "end_date": args.end_date.isoformat(),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
