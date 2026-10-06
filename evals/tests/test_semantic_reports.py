"""Separate dimensions, incomplete coverage and private/public artifacts."""

from collections.abc import Iterator
from pathlib import Path
import shutil
from uuid import uuid4

import pytest

from banking_evals.semantic.contracts import CaseResult, JudgeConfig, JudgeOutput, SemanticCase, SemanticRubric
from banking_evals.semantic.reports import build_report, public_summary, write_artifacts


@pytest.fixture
def artifact_dir() -> Iterator[Path]:
    path = Path.cwd() / "evals" / f"semantic-test-artifacts-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def test_dimensions_and_unscored_cases_have_distinct_denominators(artifact_dir: Path) -> None:
    cases = [SemanticCase(id=name, locale="es", query="Question", turns=["Question"],
        expected_behavior="Answer safely", expected_facts=[], constraints=[], account=[], transaction=[])
        for name in ("first", "missing")]
    rubric = SemanticRubric(schema_version="1", version="1", policy_summary="Safe facts.",
        criteria=[dict(id=name, dimension=name, description="Dimension", pass_anchor="Pass",
                       fail_anchor="Fail", borderline="Mixed") for name in ("confidentiality", "locale")],
        required_criteria=["confidentiality", "locale"])
    judgment = JudgeOutput(case_id="first", turns=[dict(turn=0, criteria=[
        dict(criterion_id=name, status=status, rationale="Private synthetic rationale",
             citations=[dict(turn=0)]) for name, status in (("confidentiality", "passed"), ("locale", "failed"))])])
    result = CaseResult(case_id="first", execution="completed", technical="passed", judge="completed",
                        attempts=1, evidence_sha256="a" * 64, judgment=judgment)
    report = build_report(cases, [result], dataset_sha256="b" * 64, rubric_sha256="c" * 64,
                          config=JudgeConfig(model="fake"), rubric=rubric)
    assert report["counts"]["requested_cases"] == 2
    assert report["counts"]["completed_judgments"] == 1
    assert report["counts"]["acceptance_passed"] == 0
    assert report["criteria"]["confidentiality"]["passed_cases"] == 1
    assert report["criteria"]["locale"]["passed_cases"] == 0
    assert report["criteria"]["locale"]["eligible_cases"] == 1
    assert report["cases"][1]["error_code"] == "MISSING_EVIDENCE"
    summary = public_summary(report)
    assert "Private" not in str(summary)
    assert "first" not in str(summary)
    output = artifact_dir / "report.json"
    write_artifacts(report, output)
    assert "Private" in output.read_text(encoding="utf-8")
    assert "Private" not in output.with_suffix(".md").read_text(encoding="utf-8")
    assert "Private" not in output.with_suffix(".xml").read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_artifacts(report, output)


def test_uncalibrated_success_remains_inconclusive() -> None:
    case = SemanticCase(id="case", locale="en", query="Question", turns=["Question"],
        expected_behavior="Answer", expected_facts=[], constraints=[], account=[], transaction=[])
    rubric = SemanticRubric(schema_version="1", version="1", policy_summary="Only facts",
        criteria=[dict(id="locale", dimension="locale", description="Locale", pass_anchor="Pass",
                       fail_anchor="Fail", borderline="Mixed")], required_criteria=["locale"])
    judgment = JudgeOutput(case_id="case", turns=[dict(turn=0, criteria=[dict(criterion_id="locale",
        status="passed", rationale="Correct", citations=[dict(turn=0)])])])
    result = CaseResult(case_id="case", execution="completed", technical="passed", judge="completed", judgment=judgment)
    report = build_report([case], [result], dataset_sha256="a" * 64, rubric_sha256="b" * 64,
                          config=JudgeConfig(model="fake"), rubric=rubric)
    assert report["counts"]["acceptance_inconclusive"] == 1
    rubric.acceptance_calibrated = True
    calibrated = build_report([case], [result], dataset_sha256="a" * 64, rubric_sha256="b" * 64,
                              config=JudgeConfig(model="fake"), rubric=rubric)
    assert calibrated["counts"]["acceptance_passed"] == 1
    result.technical = "failed"
    rubric.acceptance_calibrated = False
    failed = build_report([case], [result], dataset_sha256="a" * 64, rubric_sha256="b" * 64,
                         config=JudgeConfig(model="fake"), rubric=rubric)
    assert failed["counts"]["acceptance_passed"] == 0
    assert failed["counts"]["acceptance_failed"] == 1
    result.judgment.turns[0].criteria = []
    with pytest.raises(ValueError, match="criteria"):
        build_report([case], [result], dataset_sha256="a" * 64, rubric_sha256="b" * 64,
                     config=JudgeConfig(model="fake"), rubric=rubric)


def test_missing_results_are_not_counted_as_evidence() -> None:
    case = SemanticCase(id="missing", locale="en", query="Question", turns=["Question"],
        expected_behavior="Answer", expected_facts=[], constraints=[], account=[], transaction=[])
    rubric = SemanticRubric(schema_version="1", version="1", policy_summary="Only facts",
        criteria=[dict(id="locale", dimension="locale", description="Locale", pass_anchor="Pass",
                       fail_anchor="Fail", borderline="Mixed")], required_criteria=["locale"])
    result = CaseResult(case_id="missing", execution="incomplete", technical="not_applicable",
                        judge="not_run", error_code="MISSING_EVIDENCE")
    report = build_report([case], [result], dataset_sha256="a" * 64, rubric_sha256="b" * 64,
                          config=JudgeConfig(model="fake"), rubric=rubric)
    assert report["counts"]["evidence_cases"] == 0
    assert report["counts"]["completed_trajectories"] == 0
