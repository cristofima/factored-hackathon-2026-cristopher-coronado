"""Credential-free deterministic trace checks; never a semantic-quality judgment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from banking_evals.resources import repository_root
from banking_evals.semantic.contracts import EXPOSURE, SavedEvidence, SemanticCase
from banking_evals.semantic.dataset import canonical_hash, ensure_safe, fingerprint, load_dataset


def _trace_errors(case: SemanticCase, evidence: SavedEvidence) -> list[str]:
    errors: list[str] = []
    if evidence.case_id != case.id:
        errors.append("UNKNOWN_CASE")
    indices = [turn.turn for turn in evidence.turns]
    if indices != list(range(len(case.turns))):
        errors.append("MISSING_EXTRA_OR_UNORDERED_TURNS")
    if any(turn.turn >= len(case.turns) or turn.query != case.turns[turn.turn]
           for turn in evidence.turns):
        errors.append("UNKNOWN_OR_CHANGED_QUERY")
    tool_turns = [call.turn for call in evidence.tool_calls]
    if any(turn not in indices for turn in tool_turns):
        errors.append("UNKNOWN_TOOL_TURN")
    if tool_turns != sorted(tool_turns):
        errors.append("UNORDERED_TOOL_TURNS")
    sequences = [call.sequence for call in evidence.tool_calls]
    if any(sequence is not None for sequence in sequences):
        if sequences != list(range(len(sequences))):
            errors.append("INVALID_TOOL_SEQUENCE")
    return errors


def _tool_errors(case: SemanticCase, evidence: SavedEvidence) -> tuple[list[str], list[str]]:
    choice_errors: list[str] = []
    reply_errors: list[str] = []
    for server in ("account", "transaction"):
        expected = getattr(case, server)
        actual = [call for call in evidence.tool_calls if call.server == server]
        if len(expected) != len(actual):
            choice_errors.append(f"{server}:TOOL_COUNT_MISMATCH")
        for index, (reply, call) in enumerate(zip(expected, actual)):
            location = f"{server}:{index}"
            if reply.tool != call.tool:
                choice_errors.append(f"{location}:WRONG_TOOL")
            if canonical_hash(reply.arguments) != canonical_hash(call.arguments):
                choice_errors.append(f"{location}:WRONG_ARGUMENTS")
            if canonical_hash(reply.result) != canonical_hash(call.result):
                reply_errors.append(f"{location}:WRONG_RESULT")
            if reply.error != call.error:
                reply_errors.append(f"{location}:WRONG_TOOL_ERROR")
    return choice_errors, reply_errors


def evaluate_technical(
    case: SemanticCase, evidence: SavedEvidence | dict[str, Any] | None,
) -> dict[str, Any]:
    """Return independent tool_choice/task_completion booleans and controlled details.

    ReplayReply lists define required ordered calls per server, not exact call turns
    or cross-server ordering. Calls must reference valid zero-based turns. Completion
    requires the entire trace, expected replies (including deliberate denials), protocol
    success and nonempty completed answers; answer meaning is deliberately unscored.
    """
    details: dict[str, list[str]] = {"evidence": [], "tool_choice": [], "task_completion": []}
    if evidence is None:
        details["evidence"].append("MISSING_EVIDENCE")
    else:
        try:
            raw = evidence.model_dump(mode="json") if isinstance(evidence, SavedEvidence) else evidence
            ensure_safe(raw)
            saved = SavedEvidence.model_validate(raw)
            ensure_safe(case.model_dump(mode="json"))
        except (ValidationError, ValueError, TypeError):
            details["evidence"].append("INVALID_OR_SENSITIVE_EVIDENCE")
        else:
            details["evidence"] = _trace_errors(case, saved)
            choice, replies = _tool_errors(case, saved)
            details["tool_choice"] = choice
            details["task_completion"] = replies
            if not saved.protocol_passed:
                details["task_completion"].append("PROTOCOL_FAILED")
            if saved.error is not None:
                details["task_completion"].append("EXECUTION_ERROR")
            if any(not turn.completed or not turn.final_answer.strip() for turn in saved.turns):
                details["task_completion"].append("INCOMPLETE_ANSWER")
    tool_choice = not details["evidence"] and not details["tool_choice"]
    task_completion = tool_choice and not details["task_completion"]
    return {"tool_choice": tool_choice, "task_completion": task_completion, "details": details}


def evaluate_saved(dataset_path: Path, evidence_path: Path) -> dict[str, Any]:
    """Score every requested case; reject unknown, duplicate or malformed batch evidence."""
    dataset = load_dataset(dataset_path)
    raw = json.loads(evidence_path.read_text(encoding="utf-8"))
    ensure_safe(raw)
    fixture_keys = {"schema_version", "exposure", "results"}
    capture_keys = fixture_keys | {"requested_case_ids", "dataset_sha256", "rubric_sha256",
                                   "model", "model_calls", "generation_settings", "foundry_submission"}
    if (not isinstance(raw, dict) or set(raw) not in (fixture_keys, capture_keys)
            or raw["schema_version"] != "1" or raw["exposure"] != EXPOSURE
            or not isinstance(raw["results"], list)):
        raise ValueError("Invalid synthetic evidence envelope")
    if set(raw) == capture_keys and (
            raw["dataset_sha256"] != fingerprint(dataset_path)
            or raw["requested_case_ids"] != [case.id for case in dataset.cases]):
        raise ValueError("Capture dataset provenance differs")
    case_ids = {case.id for case in dataset.cases}
    by_id: dict[str, dict[str, Any]] = {}
    for item in raw["results"]:
        if not isinstance(item, dict) or not isinstance(item.get("case_id"), str):
            raise ValueError("Invalid evidence case")
        case_id = item["case_id"]
        if case_id not in case_ids or case_id in by_id:
            raise ValueError("Unknown or duplicate evidence case")
        by_id[case_id] = item
    results = [{"case_id": case.id, **evaluate_technical(case, by_id.get(case.id))}
               for case in dataset.cases]
    return {"schema_version": "1", "exposure": EXPOSURE, "evaluation": "deterministic_trace_only",
            "semantic_quality_evaluated": False, "model_calls": 0,
            "foundry_submission": "not_submitted",
            "passed": all(item["tool_choice"] and item["task_completion"] for item in results),
            "results": results}


def main(argv: list[str] | None = None) -> int:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--dataset", type=Path,
                         default=repository_root() / "evals" / "semantic_cases.json")
    command.add_argument("--evidence", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    args = command.parse_args(argv)
    if args.output.exists() or args.output.resolve() == args.evidence.resolve():
        print("Technical evaluation output must be an immutable sidecar")
        return 2
    try:
        report = evaluate_saved(args.dataset, args.evidence)
    except (ValueError, TypeError, OSError):
        report = {"schema_version": "1", "exposure": EXPOSURE, "passed": False,
                  "model_calls": 0, "semantic_quality_evaluated": False,
                  "error_code": "INVALID_OR_SENSITIVE_INPUT"}
        status = 2
    else:
        status = 0 if report["passed"] else 1
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    except OSError:
        print("Technical evaluation artifact write failed")
        return 2
    return status


if __name__ == "__main__":
    raise SystemExit(main())
