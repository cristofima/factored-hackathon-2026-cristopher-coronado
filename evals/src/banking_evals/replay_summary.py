"""Render a fail-closed protocol report without exposing model output in PR comments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def protocol_passed(result: dict[str, Any]) -> bool:
    return (
        result.get("protocol_passed") is True
        and not result.get("error")
        and isinstance(result.get("final_answer"), str)
        and bool(result["final_answer"].strip())
        and bool(result.get("response"))
        and result.get("replay_failures") == {"account": [], "transaction": []}
        and result.get("unconsumed_replies") == {"account": 0, "transaction": 0}
    )


def render_summary(report: dict[str, Any], cases: list[dict[str, Any]]) -> tuple[str, bool]:
    expected = [case["id"] for case in cases]
    results = report.get("results", [])
    observed = [result.get("case_id") for result in results]
    complete = (
        bool(expected)
        and len(set(expected)) == len(expected)
        and len(observed) == len(expected)
        and set(observed) == set(expected)
        and report.get("sample_size") == len(expected)
        and report.get("model_execution") == "real"
        and report.get("foundry_submission") == "not_submitted"
    )
    passed = complete and all(protocol_passed(result) for result in results)
    lines = [
        "## MCP Replay Smoke", "",
        f"Protocol check: **{'PASSED' if passed else 'FAILED'}**.", "",
        f"Expected cases: {len(expected)}. Recorded cases: {len(observed)}.", "",
        "Real model, synthetic MCP data. Behavior review is pending; this is not dispute",
        "quality, service authorization, baseline improvement, or a Foundry submission.", "",
        "| Case | Protocol |", "| --- | --- |",
    ]
    for case_id in expected:
        matches = [result for result in results if result.get("case_id") == case_id]
        status = "MISSING OR DUPLICATED"
        if len(matches) == 1:
            status = "PASSED" if protocol_passed(matches[0]) else "FAILED"
        safe_id = str(case_id).replace("|", "\\|").replace("`", "").replace("\n", " ")
        lines.append(f"| {safe_id} | {status} |")
    if not complete:
        lines.extend(["", "Report is incomplete or does not match the expected real-model run."])
    return "\n".join(lines) + "\n", passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        cases = json.loads(args.dataset.read_text(encoding="utf-8"))
        summary, passed = render_summary(report, cases)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        summary = (
            "## MCP Replay Smoke\n\nProtocol check: **FAILED**.\n\n"
            "Report is missing or invalid; execution is not verified.\n"
        )
        passed = False
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(summary, encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())