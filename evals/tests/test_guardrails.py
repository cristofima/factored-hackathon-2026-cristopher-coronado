"""Offline regressions for deterministic guardrail evidence."""

from __future__ import annotations

import base64
from copy import deepcopy
import json
from typing import Any

import pytest

from banking_evals.guardrails import behavior_passed, score_turn, validate_cases
from banking_evals.replay_summary import render_summary
from banking_evals.resources import resource


@pytest.fixture
def cases() -> list[dict[str, Any]]:
    return json.loads(resource("evals/guardrail_cases.json").read_text(encoding="utf-8"))


def test_dataset_has_ten_complete_cases(cases: list[dict[str, Any]]) -> None:
    validate_cases(cases)
    assert len(cases) == 10
    assert {case["locale"] for case in cases} == {"en", "es", "pt"}
    assert sum(len(case["guardrails"]) for case in cases) == 12


@pytest.mark.parametrize("representation", ["plain", "base64", "hex", "spaced"])
def test_canary_disclosure_in_stream_fails(representation: str) -> None:
    sentinel = "CANARY_DEMO_7Q9X"
    values = {
        "plain": sentinel, "base64": base64.b64encode(sentinel.encode()).decode(),
        "hex": sentinel.encode().hex(), "spaced": " ".join(sentinel),
    }
    check = {"refusal": True, "no_mcp_calls": True, "forbidden": [sentinel], "required": []}
    result = score_turn("I cannot disclose credentials.", values[representation], check, "en", [])
    assert result["no_disclosure"] is False
    assert result["refusal_indicator"] is True


@pytest.mark.parametrize("locale, answer", [
    ("en", "I cannot disclose credentials."),
    ("es", "No puedo revelar credenciales."),
    ("pt", "Não posso revelar credenciais."),
])
def test_refusal_and_tool_boundary(locale: str, answer: str) -> None:
    check = {"refusal": True, "no_mcp_calls": True, "forbidden": [], "required": []}
    assert all(score_turn(answer, "", check, locale, []).values())
    assert not score_turn(answer, "", check, locale, [{"tool": "getAccountDetails"}])["mcp_boundary"]
    assert not score_turn("Here are the requested values.", "", check, locale, [])["refusal_indicator"]


def test_required_grounding_and_nonblank_answer() -> None:
    check = {"refusal": False, "no_mcp_calls": False, "forbidden": [], "required": ["12", "USD"]}
    assert all(score_turn("USD 12", "", check, "en", [{"tool": "getAccountDetails"}]).values())
    assert not score_turn("USD 90", "", check, "en", [])["required_indicators"]
    assert not score_turn(" ", "USD 12", check, "en", [])["answer_present"]


@pytest.mark.parametrize("defect", ["duplicate", "empty-id", "partial", "locale", "switch", "positive", "query"])
def test_invalid_contract_fails(cases: list[dict[str, Any]], defect: str) -> None:
    case = cases[0]
    if defect == "duplicate":
        cases.append(deepcopy(case))
    elif defect == "empty-id":
        case["id"] = ""
    elif defect == "partial":
        case["guardrails"] = []
    elif defect == "locale":
        case["locale"] = "fr"
    elif defect == "switch":
        case["guardrails"][0]["no_mcp_calls"] = "true"
    elif defect == "query":
        case["query"] = " "
    else:
        case["guardrails"][0]["refusal"] = False
    with pytest.raises(ValueError):
        validate_cases(cases)


@pytest.fixture
def evidence(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sample_size": len(cases), "model_execution": "real",
        "foundry_submission": "not_submitted", "results": [{
            "case_id": case["id"], "protocol_passed": True,
            "final_answer": "Private answer must not appear in summary",
            "response": {"messages": [{"text": "synthetic"}]},
            "replay_failures": {"account": [], "transaction": []},
            "unconsumed_replies": {"account": 0, "transaction": 0},
            "turns": [{"completed": True, "guardrail_checks": dict.fromkeys(
                ["answer_present", "no_disclosure", "refusal_indicator",
                 "required_indicators", "mcp_boundary"], True,
            )} for _ in case["guardrails"]],
        } for case in cases],
    }


def test_complete_report_is_safe(evidence: dict[str, Any], cases: list[dict[str, Any]]) -> None:
    summary, passed = render_summary(evidence, cases)
    assert passed
    assert "## Guardrail Replay" in summary
    assert "Private answer" not in summary
    assert "not comprehensive semantic safety" in summary


@pytest.mark.parametrize("defect", ["missing-turn", "null-turns", "invalid-turn", "missing-check", "false-check", "numeric", "incomplete", "unknown"])
def test_guardrail_evidence_fails_closed(
    evidence: dict[str, Any], cases: list[dict[str, Any]], defect: str,
) -> None:
    result = evidence["results"][0]
    if defect == "missing-turn":
        result["turns"] = []
    elif defect == "null-turns":
        result["turns"] = None
    elif defect == "invalid-turn":
        result["turns"] = [None]
    elif defect == "missing-check":
        result["turns"][0]["guardrail_checks"].pop("no_disclosure")
    elif defect == "false-check":
        result["turns"][0]["guardrail_checks"]["no_disclosure"] = False
    elif defect == "numeric":
        result["turns"][0]["guardrail_checks"]["no_disclosure"] = 1
    elif defect == "incomplete":
        result["turns"][0]["completed"] = False
    else:
        result["case_id"] = "UNKNOWN"
    assert not render_summary(evidence, cases)[1]
    if defect != "unknown":
        assert not behavior_passed(result, cases[0])
