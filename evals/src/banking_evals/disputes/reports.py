"""Paired synthetic dispute replay; baseline is offline, proposed requires explicit model settings."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import platform
import sys
from time import perf_counter
from typing import Any
import unicodedata
from xml.etree import ElementTree

from banking_evals.resources import repository_root

ROOT = repository_root()

from banking_evals.dispute_replay import (
    DATASET, display_value, expanded_fingerprint, fingerprint, load_cases, score_case,
)
from banking_evals.mcp_replay import ReplayReply, ReplayServer
from banking_evals.evidence import (
    CURRENT_RESULT, available_output, controlled_error, customer_identity,
    register_result, sanitize, unique_output,
)


def rescore(report: dict[str, Any], cases: list[dict[str, Any]], dataset_hash: str) -> bool:
    if report.get("dataset_sha256") != dataset_hash:
        raise ValueError("Dataset hash differs from saved run")

    if report.get("schema_version") != 1 or report.get("system") not in {"baseline", "proposed"}:
        raise ValueError("Unsupported report schema or system")
    if report["system"] == "proposed" and not report.get("model"):
        raise ValueError("Missing model deployment evidence")
    results = report["results"]
    if len(results) != len(cases) or {result["case_id"] for result in results} != {case["id"] for case in cases}:
        raise ValueError("Missing, duplicated, or unexpected cases")
    lookup = {case["id"]: case for case in cases}
    for result in results:
        if result.get("locale") != lookup[result["case_id"]]["locale"]:
            raise ValueError("Saved locale differs from dataset")
        result["score"] = score_case(lookup[result["case_id"]], result)
    if report.get("expanded_inputs_sha256") != expanded_fingerprint(cases):
        raise ValueError("Expanded input hash missing or differs from saved run")
    report["scorer_sha256"] = fingerprint(ROOT / "evals" / "src" / "banking_evals" / "disputes" / "scoring.py")
    return all(result["score"]["passed"] for result in results)


def case_latency(result: dict[str, Any]) -> float | None:
    turns = result.get("turns", [])
    if (result.get("error") or not turns or not result["score"]["passed"]
            or any(turn.get("error") or turn.get("completed") is not True for turn in turns)
            or not result["score"]["checks"]["complete_turns"]):
        return None
    values = [turn.get("latency_seconds") for turn in turns]
    if any(type(value) not in {int, float} or not math.isfinite(value) or value < 0
           for value in values):
        return None
    return sum(values)


def compare_reports(
    baseline: dict[str, Any], proposed: dict[str, Any],
    cases: list[dict[str, Any]], dataset_hash: str,
) -> dict[str, Any]:
    if baseline.get("system") != "baseline" or proposed.get("system") != "proposed":
        raise ValueError("Comparison requires baseline and proposed reports")
    scorer_hash = fingerprint(ROOT / "evals" / "src" / "banking_evals" / "disputes" / "scoring.py")
    for report in (baseline, proposed):
        if report.get("scorer_sha256") != scorer_hash:
            raise ValueError("Comparison requires the current identical scorer fingerprint")
        if report.get("expanded_inputs_sha256") != expanded_fingerprint(cases):
            raise ValueError("Comparison requires identical frozen expanded inputs")
    rescore(baseline, cases, dataset_hash)
    rescore(proposed, cases, dataset_hash)
    baseline_results = {result["case_id"]: result for result in baseline["results"]}
    proposed_results = {result["case_id"]: result for result in proposed["results"]}
    pairs = []
    for case in cases:
        first, second = baseline_results[case["id"]], proposed_results[case["id"]]
        pairs.append({
            "case_id": case["id"], "locale": case["locale"],
            "baseline_passed": first["score"]["passed"], "proposed_passed": second["score"]["passed"],
            "structured_delta": int(second["score"]["passed"]) - int(first["score"]["passed"]),
            "baseline_seconds": case_latency(first),
            "proposed_seconds": case_latency(second),
        })
    return {"dataset_sha256": dataset_hash, "cases": pairs, "offline_or_simulated": True,
            "improvements": sum(pair["structured_delta"] > 0 for pair in pairs),
            "regressions": sum(pair["structured_delta"] < 0 for pair in pairs),
            "wins": sum(pair["structured_delta"] > 0 for pair in pairs),
            "losses": sum(pair["structured_delta"] < 0 for pair in pairs),
            "ties": sum(pair["structured_delta"] == 0 for pair in pairs),
            "baseline_failures": sum(not pair["baseline_passed"] for pair in pairs),
            "proposed_failures": sum(not pair["proposed_passed"] for pair in pairs),
            "semantic_review": "pending", "locale_review": "pending",
            "cost": "unavailable; no prices supplied",
            "limitation": "Paired structured checks, not semantic or persisted resolution evidence."}


def write_artifacts(report: dict[str, Any], output: Path) -> bool:
    report = sanitize(report)
    output = available_output(output)
    print(f"Saving redacted replay evidence to {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    results = report["results"]
    failures = sum(not result["score"]["passed"] for result in results)
    suite = ElementTree.Element("testsuite", name="dispute-structured-replay", tests=str(len(results)),
                                 failures=str(failures))
    for result in results:
        test = ElementTree.SubElement(suite, "testcase", name=result["case_id"],
                                       classname="dispute." + report["system"])
        if not result["score"]["passed"]:
            ElementTree.SubElement(test, "failure", message="Structured dispute check failed").text = ", ".join(
                result["score"]["failed_checks"])
    ElementTree.ElementTree(suite).write(output.with_suffix(".xml"), encoding="utf-8", xml_declaration=True)
    lines = ["## Dispute Replay", "", f"System: {report['system']}. Cases: {len(results)}. Failures: {failures}.",
             "", "Synthetic MCP replies; structured checks only. Semantic and locale review pending.",
             "No persisted-state, service authorization, unseen quality or production improvement claim.",
             "", "| Language | Cases | Structured Passes |", "| --- | --- | --- |"]
    for locale in ("en", "es", "pt"):
        group = [result for result in results if result["locale"] == locale]
        lines.append(f"| {locale} | {len(group)} | {sum(result['score']['passed'] for result in group)} |")
    latencies = sorted(value for result in results
                       if (value := case_latency(result)) is not None)
    lines.extend(["", f"Complete case timing: {len(latencies)}/{len(results)}. "
                  "Missing or incomplete timing is excluded, not recorded as zero."])
    if latencies:
        lines.extend(["", f"Case latency p50: {latencies[(len(latencies)-1)//2]:.4f}s; "
                      f"p95: {latencies[min(len(latencies)-1, int(len(latencies)*0.95))]:.4f}s."])
    lines.extend(["", "Priced cost: unavailable (no pricing assumptions supplied).",
                  "Safe resolution and cost per successful resolution: not established by structured replay."])
    if "comparison" in report:
        comparison = report["comparison"]
        lines.extend(["", f"Paired structured wins: {comparison['wins']}; "
                      f"ties: {comparison['ties']}; losses: {comparison['losses']}.",
                      f"Baseline failures: {comparison['baseline_failures']}; "
                      f"proposed failures: {comparison['proposed_failures']}.",
                      "Semantic review remains pending; ties can include failures in both systems."])
    output.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return bool(results) and failures == 0
