"""Capture synthetic trajectories or judge saved evidence with explicit authorization."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from banking_evals.resources import resource
from banking_evals.semantic import (
    JudgeConfig, build_report, fingerprint, load_dataset,
    load_rubric, write_artifacts,
)
from banking_evals.semantic.contracts import EXPOSURE, SemanticCase
from banking_evals.semantic.dataset import ensure_safe
from banking_evals.semantic.judge import judge_saved_evidence, project_evidence
from banking_evals.semantic.technical import evaluate_technical
from banking_evals.semantic_provider import FoundryJudgeProvider


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("mode", choices=("capture", "judge"))
    result.add_argument("--dataset", type=Path, default=resource("evals/semantic_cases.json"))
    result.add_argument("--rubric", type=Path, default=resource("evals/semantic_rubric.json"))
    result.add_argument("--evidence", type=Path)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--project-endpoint", required=True)
    result.add_argument("--model", required=True)
    result.add_argument("--authorize-model-calls", action="store_true")
    result.add_argument("--max-calls", type=int, required=True)
    result.add_argument("--timeout-seconds", type=float, default=120)
    result.add_argument("--retries", type=int, default=0)
    result.add_argument("--concurrency", type=int, default=1)
    result.add_argument("--max-context-chars", type=int, default=100000)
    return result


def validate_args(args: argparse.Namespace) -> None:
    endpoint = urlsplit(args.project_endpoint)
    if (endpoint.scheme != "https" or not endpoint.hostname or endpoint.username
            or endpoint.password or endpoint.query or endpoint.fragment):
        raise ValueError("Use an HTTPS project endpoint without credentials")
    if not args.authorize_model_calls:
        raise ValueError("Explicit synthetic-data and model-call authorization is required")
    if (not math.isfinite(args.timeout_seconds) or args.timeout_seconds <= 0
            or args.timeout_seconds > 600 or args.max_calls < 1
            or not 0 <= args.retries <= 9 or not 1 <= args.concurrency <= 16
            or args.max_context_chars < 1):
        raise ValueError("Invalid timeout or call limits")
    if args.mode == "judge" and args.evidence is None:
        raise ValueError("Judge mode requires saved evidence")
    if args.mode == "capture" and (args.evidence is not None or args.retries != 0
                                   or args.concurrency != 1):
        raise ValueError("Capture is sequential without retries or saved evidence")
    outputs = ([args.output.with_suffix(suffix) for suffix in (".json", ".md", ".xml")]
               if args.mode == "judge" else [args.output])
    if any(path.exists() for path in outputs):
        raise ValueError("Output already exists; evidence is immutable")
    if args.evidence and args.output.resolve() == args.evidence.resolve():
        raise ValueError("Judge output must be an additive sidecar")


def write_report(path: Path, report: dict[str, Any]) -> None:
    ensure_safe(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)


async def capture(args: argparse.Namespace, client: Any, cases: list[dict[str, Any]]) -> dict[str, Any]:
    from banking_evals.mcp.runner import run_case

    # A turn can make multiple model calls; enforce the budget at the client boundary.
    budgeted = BudgetedClient(client, args.max_calls)
    results = []
    parsed = load_dataset(args.dataset)
    for case in cases:
        raw = await run_case(budgeted, case, args.timeout_seconds)
        definition = next(item for item in parsed.cases if item.id == case["id"])
        results.append(project_evidence(raw, definition).model_dump(mode="json"))
    return {"schema_version": "1", "exposure": "development-exposed synthetic",
            "requested_case_ids": [case["id"] for case in cases], "results": results,
            "dataset_sha256": fingerprint(args.dataset),
            "rubric_sha256": fingerprint(args.rubric),
            "model": args.model, "model_calls": budgeted.calls,
            "generation_settings": {"timeout_seconds": args.timeout_seconds},
            "foundry_submission": "not_submitted"}


class BudgetedClient:
    """Preserve the framework client API while counting every model request."""

    def __init__(self, client: Any, maximum: int) -> None:
        self.client = client
        self.maximum = maximum
        self.calls = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)

    def get_response(self, *args: Any, **kwargs: Any) -> Any:
        if self.calls >= self.maximum:
            raise RuntimeError("Model call budget exhausted")
        self.calls += 1
        return self.client.get_response(*args, **kwargs)


async def main_async(args: argparse.Namespace) -> int:
    validate_args(args)
    dataset = load_dataset(args.dataset)
    load_rubric(args.rubric)
    if args.mode == "judge":
        load_capture(args, dataset.cases)
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import AzureCliCredential

    async with AzureCliCredential() as credential:
        client = FoundryChatClient(project_endpoint=args.project_endpoint,
                                   model=args.model, credential=credential)
        report = await execute(args, client)
    if args.mode == "capture":
        write_report(args.output, report)
        checks = [evaluate_technical(case, item)
                  for case, item in zip(dataset.cases, report["results"], strict=True)]
        return 0 if all(check["task_completion"] for check in checks) else 1
    write_artifacts(report, args.output)
    counts = report["counts"]
    return 0 if (counts["completed_judgments"] == counts["requested_cases"]
                 and counts["technical_failures"] == 0) else 1


async def execute(args: argparse.Namespace, client: Any) -> dict[str, Any]:
    validate_args(args)
    dataset = load_dataset(args.dataset)
    rubric = load_rubric(args.rubric)
    if args.mode == "capture":
        return await capture(args, client, [case.model_dump(mode="json") for case in dataset.cases])
    saved = load_capture(args, dataset.cases)
    config = JudgeConfig(model=args.model, timeout_seconds=args.timeout_seconds,
                         max_attempts=args.retries + 1, max_calls=args.max_calls,
                         concurrency=args.concurrency, max_context_chars=args.max_context_chars,
                         generation_settings={"tool_choice": "none", "store": False})
    results = await judge_saved_evidence(dataset.cases, rubric, saved["results"],
                                        FoundryJudgeProvider(client), config)
    return build_report(dataset.cases, results, dataset_sha256=fingerprint(args.dataset),
                        rubric_sha256=fingerprint(args.rubric), config=config, rubric=rubric)


def load_capture(args: argparse.Namespace, cases: list[SemanticCase]) -> dict[str, Any]:
    saved = json.loads(args.evidence.read_text(encoding="utf-8"))
    ensure_safe(saved)
    if (not isinstance(saved, dict) or saved.get("exposure") != EXPOSURE
            or saved.get("schema_version") != "1"
            or saved.get("requested_case_ids") != [case.id for case in cases]
            or saved.get("dataset_sha256") != fingerprint(args.dataset)
            or saved.get("rubric_sha256") != fingerprint(args.rubric)
            or not isinstance(saved.get("results"), list)):
        raise ValueError("Invalid synthetic capture envelope")
    return saved


def main() -> int:
    command = parser()
    args = command.parse_args()
    try:
        return asyncio.run(main_async(args))
    except (ValueError, OSError, ImportError):
        print("Semantic evaluation configuration or input error")
        return 2
    except Exception:
        print("Semantic evaluation provider error")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
