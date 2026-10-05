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


from banking_evals.disputes.baseline import run_baseline
from banking_evals.disputes.reports import rescore, compare_reports, write_artifacts

async def main_async(args: argparse.Namespace) -> int:
    metadata, cases = load_cases(args.dataset)
    dataset_hash = fingerprint(args.dataset)
    if args.rescore:
        report = json.loads(args.rescore.read_text(encoding="utf-8"))
    else:
        if args.system == "baseline":
            results = [await execute_case(run_baseline, case, args.timeout_seconds) for case in cases]
        else:
            if not args.project_endpoint or not args.model:
                raise ValueError("Proposed replay requires explicit endpoint and model")
            from banking_evals.run_mcp_replay import run_case
            from agent_framework.foundry import FoundryChatClient
            from azure.identity.aio import AzureCliCredential
            async with AzureCliCredential() as credential:
                client = FoundryChatClient(project_endpoint=args.project_endpoint, model=args.model,
                                           credential=credential)
                async def proposed(case: dict[str, Any]) -> dict[str, Any]:
                    return await run_case(client, case, args.timeout_seconds)

                results = [await execute_case(proposed, case, args.timeout_seconds) for case in cases]
        report = {
            "schema_version": 1, "dataset_version": metadata["version"],
            "dataset_sha256": dataset_hash, "split": metadata["split"], "system": args.system,
            "results": results, "created_at": datetime.now(timezone.utc).isoformat(),
            "model": args.model, "model_execution": "real" if args.system == "proposed" else "none",
            "offline_or_simulated": True, "foundry_submission": "not_submitted",
            "prompt_sha256": fingerprint(ROOT / "app/agent/src/app/agents/azure_chat/transaction_agent.py"),
            "baseline_sha256": fingerprint(ROOT / "evals/src/banking_evals/disputes/baseline.py"),
            "semantic_review": "pending",
            "python_version": platform.python_version(),
            "scorer_sha256": fingerprint(ROOT / "evals/src/banking_evals/disputes/scoring.py"),
            "contract_sha256": {
                name: fingerprint(ROOT / "app/business-api" / name / "src" / f"banking_{name}" / "mcp_tools.py")
                for name in ("account", "transaction")
            },
            "timeout_seconds": args.timeout_seconds,
            "expanded_inputs_sha256": expanded_fingerprint(cases),
            "operator_adjudication": "not evaluated: approved operator adjudication is outside replay coverage",
            "identity_acceptance": "not established: synthetic internal envelope, no JWT introspection",
        }
    report = sanitize(report)
    passed = rescore(report, cases, dataset_hash)
    if args.compare_baseline:
        baseline = sanitize(json.loads(args.compare_baseline.read_text(encoding="utf-8")))
        report["comparison"] = compare_reports(baseline, report, cases, dataset_hash)
    output = args.output or unique_output(ROOT / "evals" / "results", f"dispute-{report['system']}")
    return 0 if write_artifacts(report, output) and passed else 1


async def execute_case(runner: Any, case: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    token = CURRENT_RESULT.set(None)
    try:
        async with asyncio.timeout(timeout_seconds):
            return await runner(case)
    except Exception as error:
        result = CURRENT_RESULT.get() or {"case_id": case["id"], "locale": case["locale"],
                                          "turns": [], "tool_calls": []}
        result.update(protocol_passed=False, error=controlled_error(error))
        return sanitize(result)
    finally:
        CURRENT_RESULT.reset(token)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", choices=("baseline", "proposed"), default="baseline")
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--rescore", type=Path)
    parser.add_argument("--compare-baseline", type=Path)
    parser.add_argument("--project-endpoint")
    parser.add_argument("--model")
    parser.add_argument("--timeout-seconds", type=float, default=120)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("Timeout must be positive")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())