"""Separate semantic dimensions and controlled summaries with complete coverage."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from banking_evals.semantic.contracts import CaseResult, JudgeConfig, SemanticCase, SemanticRubric
from banking_evals.semantic.dataset import ensure_safe


def _acceptance(result: CaseResult, rubric: SemanticRubric) -> str:
    if result.technical == "failed" or result.execution == "execution_error":
        return "failed"
    if not rubric.acceptance_calibrated:
        return "inconclusive"
    if result.execution != "completed" or result.technical != "passed" or result.judge != "completed":
        return "inconclusive"
    if result.judgment is None:
        return "inconclusive"
    required = set(rubric.required_criteria)
    statuses = [criterion.status for turn in result.judgment.turns
                for criterion in turn.criteria if criterion.criterion_id in required]
    if "failed" in statuses:
        return "failed"
    if not statuses or "not_applicable" in statuses:
        return "inconclusive"
    return "passed"


def build_report(cases: list[SemanticCase], results: list[CaseResult], *, dataset_sha256: str,
                 rubric_sha256: str, config: JudgeConfig, rubric: SemanticRubric) -> dict[str, Any]:
    """Retain every requested trajectory and never average independent dimensions."""
    ids = [case.id for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate requested cases")
    indexed: dict[str, CaseResult] = {}
    for result in results:
        if result.case_id not in ids or result.case_id in indexed:
            raise ValueError("Unknown or duplicate report case")
        case = next(case for case in cases if case.id == result.case_id)
        if result.judge == "completed":
            judgment = result.judgment
            if result.execution != "completed" or judgment is None or judgment.case_id != case.id:
                raise ValueError("Inconsistent completed judgment")
            turn_ids = [turn.turn for turn in judgment.turns]
            if sorted(turn_ids) != list(range(len(case.turns))):
                raise ValueError("Incomplete report judgment turns")
            expected = {criterion.id for criterion in rubric.criteria}
            for turn in judgment.turns:
                criterion_ids = [criterion.criterion_id for criterion in turn.criteria]
                if len(criterion_ids) != len(expected) or set(criterion_ids) != expected:
                    raise ValueError("Incomplete report judgment criteria")
        elif result.judgment is not None:
            raise ValueError("Judgment present without completed status")
        indexed[result.case_id] = result
    complete = [indexed.get(case.id) or CaseResult(
        case_id=case.id, execution="incomplete", technical="not_applicable", judge="not_run",
        error_code="MISSING_EVIDENCE", rubric_version=rubric.version,
    ) for case in cases]
    criteria: dict[str, dict[str, int]] = {}
    for definition in rubric.criteria:
        statuses: list[str] = []
        passed_cases = 0
        eligible_cases = 0
        for result in complete:
            if result.execution != "completed" or result.judgment is None or result.judge != "completed":
                continue
            judgments = [criterion for turn in result.judgment.turns for criterion in turn.criteria
                         if criterion.criterion_id == definition.id]
            statuses.extend(criterion.status for criterion in judgments)
            if judgments and all(criterion.status != "not_applicable" for criterion in judgments):
                eligible_cases += 1
                passed_cases += all(criterion.status == "passed" for criterion in judgments)
        counts = Counter(statuses)
        criteria[definition.id] = {
            "passed_turns": counts["passed"], "failed_turns": counts["failed"],
            "not_applicable_turns": counts["not_applicable"],
            "eligible_cases": eligible_cases, "passed_cases": passed_cases,
            "requested_cases": len(cases),
        }
    acceptance = [_acceptance(result, rubric) for result in complete]
    report: dict[str, Any] = {
        "schema_version": "1", "exposure": "development-exposed synthetic",
        "foundry_submission": "not_submitted", "acceptance_calibrated": rubric.acceptance_calibrated,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provenance": {"dataset_sha256": dataset_sha256, "rubric_sha256": rubric_sha256,
                       "rubric_version": rubric.version, "judge_config": config.model_dump(mode="json")},
        "counts": {
            "requested_cases": len(cases),
            "evidence_cases": sum(result.error_code != "MISSING_EVIDENCE" for result in indexed.values()),
            "attempted_trajectories": sum(result.error_code != "MISSING_EVIDENCE" for result in indexed.values()),
            "completed_trajectories": sum(result.execution == "completed" for result in complete),
            "execution_errors": sum(result.execution == "execution_error" for result in complete),
            "incomplete_trajectories": sum(result.execution == "incomplete" for result in complete),
            "attempted_judgments": sum(result.attempts > 0 for result in complete),
            "judge_calls": sum(result.attempts for result in complete),
            "completed_judgments": sum(result.judge == "completed" for result in complete),
            "judge_errors": sum(result.judge == "judge_error" for result in complete),
            "unscorable": sum(result.judge == "unscorable" for result in complete),
            "technical_failures": sum(result.technical == "failed" for result in complete),
            "acceptance_passed": acceptance.count("passed"),
            "acceptance_failed": acceptance.count("failed"),
            "acceptance_inconclusive": acceptance.count("inconclusive"),
        },
        "criteria": criteria,
        "cases": [dict(result.model_dump(mode="json"), acceptance=status)
                  for result, status in zip(complete, acceptance, strict=True)],
    }
    ensure_safe(report)
    return report


def public_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Only fixed status/count fields; omit model identifiers, IDs and rationales."""
    count_names = (
        "requested_cases", "evidence_cases", "attempted_trajectories", "completed_trajectories",
        "execution_errors", "incomplete_trajectories", "attempted_judgments", "judge_calls",
        "completed_judgments", "judge_errors", "unscorable", "technical_failures",
        "acceptance_passed", "acceptance_failed", "acceptance_inconclusive",
    )
    counts = {name: int(report["counts"][name]) for name in count_names}
    allowed = {"confidentiality", "helpfulness", "injection_resistance", "groundedness", "relevance", "locale"}
    metrics = {"passed_turns", "failed_turns", "not_applicable_turns", "eligible_cases", "passed_cases", "requested_cases"}
    criteria = {name: {key: int(value) for key, value in values.items() if key in metrics}
                for name, values in report["criteria"].items() if name in allowed}
    return {"foundry_submission": "not_submitted", "counts": counts, "criteria": criteria}


def write_artifacts(report: dict[str, Any], output: str | Path) -> None:
    """Write a private JSON sidecar and controlled Markdown/JUnit without overwriting."""
    ensure_safe(report)
    stem = Path(output).with_suffix("")
    paths = [stem.with_suffix(suffix) for suffix in (".json", ".md", ".xml")]
    if any(path.exists() for path in paths):
        raise FileExistsError("Semantic artifacts already exist")
    stem.parent.mkdir(parents=True, exist_ok=True)
    summary = public_summary(report)
    lines = ["# Semantic evaluation", "", "Foundry submission: not_submitted", "",
             "| Metric | Count |", "| --- | ---: |"]
    lines.extend(f"| {key} | {value} |" for key, value in summary["counts"].items())
    lines.extend(["", "| Criterion | Passed cases | Eligible cases | Requested cases | Failed turns |",
                  "| --- | ---: | ---: | ---: | ---: |"])
    lines.extend(f"| {name} | {metrics['passed_cases']} | {metrics['eligible_cases']} | "
                 f"{metrics['requested_cases']} | {metrics['failed_turns']} |"
                 for name, metrics in summary["criteria"].items())
    lines.extend(["", "Calibration, authorization and runtime acceptance remain separate gates."])
    suite = Element("testsuite", name="semantic-replay", tests=str(summary["counts"]["requested_cases"]),
                    failures=str(summary["counts"]["acceptance_failed"]),
                    skipped=str(summary["counts"]["acceptance_inconclusive"]))
    for index, case in enumerate(report["cases"]):
        test = SubElement(suite, "testcase", name=f"semantic-case-{index}")
        if case["acceptance"] == "failed":
            SubElement(test, "failure", message="Semantic required criterion failed")
        elif case["acceptance"] != "passed":
            SubElement(test, "skipped", message="Acceptance inconclusive")
    content = [json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
               "\n".join(lines) + "\n", tostring(suite, encoding="unicode") + "\n"]
    for path, text in zip(paths, content, strict=True):
        with path.open("x", encoding="utf-8") as handle:
            handle.write(text)
