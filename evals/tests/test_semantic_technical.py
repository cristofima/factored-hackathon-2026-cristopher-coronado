"""Offline deterministic trace and credential-free CLI regressions."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import shutil
from typing import Any, Iterator
from uuid import uuid4

import pytest

from banking_evals.resources import repository_root
from banking_evals.semantic import technical
from banking_evals.semantic.contracts import SavedEvidence, SemanticCase
from banking_evals.semantic.dataset import load_dataset


@pytest.fixture
def workspace() -> Iterator[Path]:
    path = repository_root() / "evals" / f".technical-test-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


@pytest.fixture
def case() -> SemanticCase:
    return next(case for case in load_dataset().cases if case.id == "SEM-OWNED-BALANCE")


@pytest.fixture
def evidence(case: SemanticCase) -> dict[str, Any]:
    fixture = json.loads((repository_root() / "evals" / "semantic_technical_evidence.json")
                         .read_text(encoding="utf-8"))
    return next(item for item in fixture["results"] if item["case_id"] == case.id)


@pytest.mark.parametrize("matching_fingerprint", [True, False])
def test_capture_envelope_requires_dataset_provenance(
    workspace: Path, matching_fingerprint: bool,
) -> None:
    root = repository_root() / "evals"
    dataset_path = root / "semantic_cases.json"
    saved = json.loads((root / "semantic_technical_evidence.json").read_text(encoding="utf-8"))
    saved.update({
        "requested_case_ids": [case.id for case in load_dataset().cases],
        "dataset_sha256": technical.fingerprint(dataset_path) if matching_fingerprint else "changed",
        "rubric_sha256": technical.fingerprint(root / "semantic_rubric.json"),
        "model": "synthetic-test", "model_calls": 0, "generation_settings": {},
        "foundry_submission": "not_submitted",
    })
    evidence_path = workspace / "capture.json"
    evidence_path.write_text(json.dumps(saved), encoding="utf-8")
    if matching_fingerprint:
        assert technical.evaluate_saved(dataset_path, evidence_path)["passed"] is True
    else:
        with pytest.raises(ValueError, match="provenance"):
            technical.evaluate_saved(dataset_path, evidence_path)


def test_positive_fixture_covers_every_case() -> None:
    root = repository_root() / "evals"
    report = technical.evaluate_saved(root / "semantic_cases.json", root / "semantic_technical_evidence.json")
    assert report["passed"] is True
    assert report["model_calls"] == 0
    assert report["semantic_quality_evaluated"] is False
    assert len(report["results"]) == len(load_dataset().cases)
    assert all(item["tool_choice"] and item["task_completion"] for item in report["results"])


def test_normalized_evidence_and_no_semantic_judgment(case: SemanticCase, evidence: dict[str, Any]) -> None:
    evidence["turns"][0]["final_answer"] = "Meaning is not judged."
    assert technical.evaluate_technical(case, SavedEvidence.model_validate(evidence)) == {
        "tool_choice": True, "task_completion": True,
        "details": {"evidence": [], "tool_choice": [], "task_completion": []},
    }


@pytest.mark.parametrize("mutation", [
    "missing_turn", "extra_turn", "duplicate_turn", "unordered_turn", "changed_query",
    "changed_case", "unknown_tool_turn", "unordered_tool_turns", "invalid_sequence",
    "unknown_field", "unknown_server", "negative_turn", "sensitive",
])
def test_invalid_evidence_fails_both_checks(
    case: SemanticCase, evidence: dict[str, Any], mutation: str,
) -> None:
    if mutation == "missing_turn":
        evidence["turns"].pop()
    elif mutation == "extra_turn":
        evidence["turns"].append({**evidence["turns"][0], "turn": 2})
    elif mutation == "duplicate_turn":
        evidence["turns"][1]["turn"] = 0
    elif mutation == "unordered_turn":
        evidence["turns"].reverse()
    elif mutation == "changed_query":
        evidence["turns"][0]["query"] = "changed"
    elif mutation == "changed_case":
        evidence["case_id"] = "unknown"
    elif mutation == "unknown_tool_turn":
        evidence["tool_calls"][0]["turn"] = 2
    elif mutation == "unordered_tool_turns":
        evidence["tool_calls"] = [{**evidence["tool_calls"][0], "turn": 1},
                                  {**evidence["tool_calls"][0], "turn": 0}]
    elif mutation == "invalid_sequence":
        evidence["tool_calls"][0]["sequence"] = 1
    elif mutation == "unknown_field":
        evidence["unknown"] = True
    elif mutation == "unknown_server":
        evidence["tool_calls"][0]["server"] = "unknown"
    elif mutation == "negative_turn":
        evidence["turns"][0]["turn"] = -1
    elif mutation == "sensitive":
        evidence["turns"][0]["final_answer"] = "Bearer synthetic-credential"
    result = technical.evaluate_technical(case, evidence)
    assert result["tool_choice"] is False
    assert result["task_completion"] is False
    assert result["details"]["evidence"]


@pytest.mark.parametrize("mutation", ["missing", "extra", "tool", "server", "arguments", "argument_type"])
def test_wrong_tool_choice_fails_completion(
    case: SemanticCase, evidence: dict[str, Any], mutation: str,
) -> None:
    call = evidence["tool_calls"][0]
    if mutation == "missing":
        evidence["tool_calls"] = []
    elif mutation == "extra":
        evidence["tool_calls"].append(deepcopy(call))
        evidence["tool_calls"][1]["sequence"] = 1
    elif mutation == "tool":
        call["tool"] = "unknownTool"
    elif mutation == "server":
        call["server"] = "transaction"
    elif mutation == "arguments":
        call["arguments"]["extra"] = "value"
    else:
        call["arguments"]["product_number"] = 1
    result = technical.evaluate_technical(case, evidence)
    assert result["tool_choice"] is False
    assert result["task_completion"] is False
    assert result["details"]["tool_choice"]


@pytest.mark.parametrize("mutation", ["result", "error", "protocol", "execution", "incomplete", "blank"])
def test_completion_failure_preserves_correct_tool_choice(
    case: SemanticCase, evidence: dict[str, Any], mutation: str,
) -> None:
    if mutation == "result":
        evidence["tool_calls"][0]["result"] = {}
    elif mutation == "error":
        evidence["tool_calls"][0]["error"] = "Unexpected denial"
    elif mutation == "protocol":
        evidence["protocol_passed"] = False
    elif mutation == "execution":
        evidence["error"] = {"code": "EXECUTION_FAILED"}
    elif mutation == "incomplete":
        evidence["turns"][0]["completed"] = False
    else:
        evidence["turns"][0]["final_answer"] = "  "
    result = technical.evaluate_technical(case, evidence)
    assert result["tool_choice"] is True
    assert result["task_completion"] is False
    assert result["details"]["task_completion"]


def test_missing_evidence(case: SemanticCase) -> None:
    assert technical.evaluate_technical(case, None)["details"]["evidence"] == ["MISSING_EVIDENCE"]


def test_empty_trace_is_not_completed(case: SemanticCase, evidence: dict[str, Any]) -> None:
    evidence["turns"] = []
    evidence["tool_calls"] = []
    result = technical.evaluate_technical(case, evidence)
    assert result["tool_choice"] is False
    assert result["task_completion"] is False


def test_unexpected_tool_on_no_tool_case(evidence: dict[str, Any]) -> None:
    no_tool_case = next(case for case in load_dataset().cases if case.id == "SEM-CONFIDENTIALITY")
    evidence["case_id"] = no_tool_case.id
    evidence["turns"] = [{"turn": 0, "query": no_tool_case.query,
                          "completed": True, "final_answer": "Synthetic answer"}]
    result = technical.evaluate_technical(no_tool_case, evidence)
    assert result["tool_choice"] is False
    assert result["task_completion"] is False


def test_expected_denial_is_completed_but_missing_denial_is_not() -> None:
    root = repository_root() / "evals"
    case = next(case for case in load_dataset().cases if case.id == "SEM-OWNERSHIP-DENIAL")
    rows = json.loads((root / "semantic_technical_evidence.json").read_text(encoding="utf-8"))["results"]
    evidence = next(item for item in rows if item["case_id"] == case.id)
    assert technical.evaluate_technical(case, evidence)["task_completion"] is True
    evidence["tool_calls"][0]["error"] = None
    result = technical.evaluate_technical(case, evidence)
    assert result["tool_choice"] is True
    assert result["task_completion"] is False


def test_tools_are_not_assigned_invented_turn_expectations(case: SemanticCase, evidence: dict[str, Any]) -> None:
    evidence["tool_calls"][0]["turn"] = 1
    evidence["tool_calls"][0].pop("sequence")
    assert technical.evaluate_technical(case, evidence)["task_completion"] is True


def test_reply_order_is_required_per_server(case: SemanticCase, evidence: dict[str, Any]) -> None:
    second = case.account[0].model_copy(update={"arguments": {"product_number": "SYNTHETIC-002"}})
    case = case.model_copy(update={"account": [case.account[0], second]})
    evidence["tool_calls"].append({**evidence["tool_calls"][0], "arguments": second.arguments, "sequence": 1})
    assert technical.evaluate_technical(case, evidence)["task_completion"] is True
    evidence["tool_calls"][0]["arguments"], evidence["tool_calls"][1]["arguments"] = (
        evidence["tool_calls"][1]["arguments"], evidence["tool_calls"][0]["arguments"],
    )
    assert technical.evaluate_technical(case, evidence)["tool_choice"] is False


@pytest.mark.parametrize("mutation", ["unknown", "duplicate", "missing", "malformed", "extra_field", "sensitive"])
def test_batch_and_cli_fail_closed(workspace: Path, mutation: str) -> None:
    root = repository_root() / "evals"
    raw = json.loads((root / "semantic_technical_evidence.json").read_text(encoding="utf-8"))
    if mutation == "unknown":
        raw["results"][0]["case_id"] = "UNKNOWN"
    elif mutation == "duplicate":
        raw["results"].append(raw["results"][0])
    elif mutation == "missing":
        raw["results"].pop()
    elif mutation == "extra_field":
        raw["extra"] = True
    elif mutation == "sensitive":
        raw["results"][0]["password"] = "synthetic"
    source = workspace / "evidence.json"
    source.write_text("{" if mutation == "malformed" else json.dumps(raw), encoding="utf-8")
    output = workspace / "report.json"
    code = technical.main(["--dataset", str(root / "semantic_cases.json"),
                           "--evidence", str(source), "--output", str(output)])
    assert code == (1 if mutation == "missing" else 2)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert report["model_calls"] == 0
    assert "synthetic-credential" not in output.read_text(encoding="utf-8")


def test_cli_positive_and_immutable_sidecar(workspace: Path) -> None:
    source = repository_root() / "evals" / "semantic_technical_evidence.json"
    output = workspace / "report.json"
    argv = ["--evidence", str(source), "--output", str(output)]
    assert technical.main(argv) == 0
    before = output.read_bytes()
    assert technical.main(argv) == 2
    assert output.read_bytes() == before
    assert technical.main(["--evidence", str(source), "--output", str(source)]) == 2
