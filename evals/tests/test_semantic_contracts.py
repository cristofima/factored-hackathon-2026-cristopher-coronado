"""Strict schema and evidence citation regressions."""

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from banking_evals.semantic.contracts import JudgeConfig, JudgeOutput, SavedEvidence, SemanticDataset, SemanticRubric


def rubric() -> SemanticRubric:
    return SemanticRubric(schema_version="1", version="1", policy_summary="Use supplied facts.",
        criteria=[dict(id=name, dimension=name, description="Evaluate this dimension.",
                       pass_anchor="Supported", fail_anchor="Unsupported", borderline="Uncertain")
                  for name in ("confidentiality", "locale")],
        required_criteria=["confidentiality", "locale"])


def evidence() -> SavedEvidence:
    return SavedEvidence(case_id="case", protocol_passed=True,
        turns=[dict(turn=0, query="Balance?", completed=True, final_answer="Ten dollars.")],
        tool_calls=[dict(turn=0, server="account", tool="balance", arguments={}, result={"balance": 10})])


def output() -> dict[str, Any]:
    return dict(case_id="case", turns=[dict(turn=0, criteria=[
        dict(criterion_id=name, status="passed", rationale="Supported by this turn.",
             citations=[dict(turn=0, tool_index=0)], confidence=0.9)
        for name in ("confidentiality", "locale")])])


def test_valid_output_cites_real_tools() -> None:
    JudgeOutput.model_validate(output()).validate_references(evidence(), rubric())


@pytest.mark.parametrize("mutation", ["extra", "case", "turn", "duplicate", "missing", "tool", "future"])
def test_invalid_judgment_is_rejected(mutation: str) -> None:
    value = output()
    criteria = value["turns"][0]["criteria"]
    if mutation == "extra":
        value["unexpected"] = True
    elif mutation == "case":
        value["case_id"] = "foreign"
    elif mutation == "turn":
        value["turns"][0]["turn"] = 1
    elif mutation == "duplicate":
        criteria.append(deepcopy(criteria[0]))
    elif mutation == "missing":
        criteria.pop()
    elif mutation == "tool":
        criteria[0]["citations"][0]["tool_index"] = 1
    else:
        criteria[0]["citations"][0]["turn"] = 1
    with pytest.raises((ValidationError, ValueError)):
        JudgeOutput.model_validate(value).validate_references(evidence(), rubric())


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), -0.1, 1.1, "0.9"])
def test_confidence_is_finite_strict_probability(confidence: Any) -> None:
    value = output()
    value["turns"][0]["criteria"][0]["confidence"] = confidence
    with pytest.raises(ValidationError):
        JudgeOutput.model_validate(value)


@pytest.mark.parametrize("settings", [dict(max_calls=-1), dict(max_attempts=0), dict(concurrency=True),
                                      dict(timeout_seconds=0.0), dict(max_context_chars=0)])
def test_judge_limits_are_validated(settings: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        JudgeConfig(model="offline", **settings)


def test_dataset_rejects_duplicate_ids_and_version() -> None:
    case = dict(id="case", locale="en", query="Balance?", turns=["Balance?"],
                expected_behavior="Answer grounded balance", expected_facts=[], constraints=[], account=[], transaction=[])
    with pytest.raises(ValidationError):
        SemanticDataset(schema_version="1", exposure="development-exposed synthetic", cases=[case, case])
    with pytest.raises(ValidationError):
        SemanticDataset(schema_version="2", exposure="development-exposed synthetic", cases=[case])


def test_rubric_rejects_missing_required_criterion() -> None:
    value = rubric().model_dump()
    value["required_criteria"].append("helpfulness")
    with pytest.raises(ValidationError):
        SemanticRubric.model_validate(value)
