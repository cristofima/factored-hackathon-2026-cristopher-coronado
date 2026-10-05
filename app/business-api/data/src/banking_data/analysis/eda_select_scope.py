from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select bounded ingest scope from EDA profile")
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--max-null-rate", type=float, default=0.3)
    parser.add_argument("--max-duplicate-rate", type=float, default=0.05)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    table_checks: dict[str, dict[str, object]] = {}

    for table_name, table_data in profile.get("tables", {}).items():
        row_count = int(table_data.get("row_count", 0))
        duplicates = int(table_data.get("duplicate_key_count", 0))
        duplicate_rate = (duplicates / row_count) if row_count else 0.0

        critical_columns = ["customer_id", "product_id", "currency", "current_balance", "amount"]
        columns = table_data.get("columns", {})
        high_null_columns = []
        for column_name in critical_columns:
            column_stats = columns.get(column_name)
            if not column_stats:
                continue
            if float(column_stats.get("null_rate", 0.0)) > args.max_null_rate:
                high_null_columns.append(column_name)

        table_checks[table_name] = {
            "row_count": row_count,
            "duplicate_rate": round(duplicate_rate, 6),
            "high_null_critical_columns": high_null_columns,
            "pass": duplicate_rate <= args.max_duplicate_rate and not high_null_columns,
        }

    partition_health = profile.get("transactions_partition_health", {})
    missing_days = int(partition_health.get("missing_day_count", 0))
    scope = {
        "source_root": profile.get("source_root"),
        "customer_filter": profile.get("customer_filter", []),
        "approved_transaction_window": {
            "start_date": args.start_date.isoformat(),
            "end_date": args.end_date.isoformat(),
        },
        "load_dimensions": ["branches.csv", "customers.csv", "products.csv"],
        "load_transactions": True,
        "gates": {
            "partitions_complete": missing_days == 0,
            "max_null_rate": args.max_null_rate,
            "max_duplicate_rate": args.max_duplicate_rate,
            "tables": table_checks,
        },
    }

    scope["approved"] = scope["gates"]["partitions_complete"] and all(
        check.get("pass", False) for check in table_checks.values()
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(scope, indent=2), encoding="utf-8")
    print(f"Scope manifest created: {args.output} (approved={scope['approved']})")


if __name__ == "__main__":
    main()
