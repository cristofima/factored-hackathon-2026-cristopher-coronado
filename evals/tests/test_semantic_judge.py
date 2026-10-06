"""Deterministic adapter failures, coverage and transport budgeting."""

from copy import deepcopy
from typing import Any
import asyncio

import pytest

from banking_evals.semantic.contracts import JudgeConfig, SemanticCase, SemanticRubric
from banking_evals.semantic.judge import TransportError, judge_saved_evidence


def case(case_id: str = "case") -> SemanticCase:
    return SemanticCase(id=case_id, locale="es", query="Balance?", turns=["Balance?"],
        expected_behavior="Answer balance", expected_facts=["Ten dollars"], constraints=[], account=[], transaction=[])


def rubric() -> SemanticRubric:
    return SemanticRubric(schema_version="1", version="1", policy_summary="Only supplied facts.",
        criteria=[dict(id="locale", dimension="locale", description="Stored locale",
                       pass_anchor="Spanish", fail_anchor="English", borderline="Mixed")], required_criteria=["locale"])


def raw(case_id: str = "case") -> dict[str, Any]:
    return dict(case_id=case_id, protocol_passed=True, error=None,
        turns=[dict(turn=0, query="Balance?", completed=True, final_answer="El saldo es diez dólares.")], tool_calls=[])


class FakeAdapter:
    def __init__(self, outcomes: list[str]) -> None:
        self.outcomes = outcomes
        self.payloads: list[dict[str, Any]] = []

    async def judge(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.payloads.append(payload)
        outcome = self.outcomes.pop(0)
        if outcome == "transport":
            raise TransportError("Private provider exception")
        if outcome == "timeout":
            await asyncio.sleep(1)
        if outcome == "provider":
            raise RuntimeError("Private provider exception")
        if outcome == "invalid":
            return {"raw_response": "private"}
        return dict(case_id=payload["scenario"]["id"], turns=[dict(turn=0, criteria=[
            dict(criterion_id="locale", status=outcome, rationale="Evidence language differs.",
                 citations=[dict(turn=0)])])])


@pytest.mark.asyncio
@pytest.mark.parametrize("answer, verdict", [
    ("El saldo disponible es de diez dólares.", "passed"),
    ("I can't show another customer's balance.", "failed"),
    ("I can’t show another customer’s balance.", "failed"),
    ("No puedo ayudar con ninguna consulta bancaria.", "failed"),
    ("El banco garantiza diez dólares de intereses diarios.", "failed"),
    ("El saldo is ten dollars.", "failed"),
])
async def test_judges_paraphrase_without_phrase_scoring_or_input_mutation(
    answer: str, verdict: str,
) -> None:
    evidence = raw()
    evidence["turns"][0]["final_answer"] = answer
    original = deepcopy(evidence)
    adapter = FakeAdapter([verdict])
    results = await judge_saved_evidence([case()], rubric(), [evidence], adapter, JudgeConfig(model="fake"))
    assert results[0].judge == "completed"
    assert results[0].attempts == 1
    assert evidence == original
    assert adapter.payloads[0]["scenario"]["locale"] == "es"
    assert adapter.payloads[0]["quoted_evidence"]["turns"][0]["final_answer"] == answer
    assert results[0].judgment is not None
    assert results[0].judgment.turns[0].criteria[0].status == verdict
    assert "account" not in adapter.payloads[0]["scenario"]


@pytest.mark.asyncio
@pytest.mark.parametrize("outcomes, attempts, status", [
    (["transport", "passed"], 2, "completed"), (["failed"], 1, "completed"),
    (["invalid"], 1, "judge_error"), (["provider"], 1, "judge_error"),
    (["timeout", "timeout"], 2, "judge_error"),
])
async def test_only_transport_is_retried(outcomes: list[str], attempts: int, status: str) -> None:
    adapter = FakeAdapter(outcomes)
    result = (await judge_saved_evidence([case()], rubric(), [raw()], adapter,
        JudgeConfig(model="fake", timeout_seconds=0.01)))[0]
    assert result.attempts == attempts
    assert result.judge == status
    assert "Private" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_global_budget_accounts_every_attempt_and_all_cases() -> None:
    adapter = FakeAdapter(["transport", "passed"])
    results = await judge_saved_evidence([case(), case("second")], rubric(), [raw(), raw("second")],
        adapter, JudgeConfig(model="fake", max_calls=1))
    assert sum(result.attempts for result in results) == 1
    assert len(results) == 2
    assert all(result.error_code == "CALL_BUDGET_EXHAUSTED" for result in results)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind, execution, judge", [
    ("missing", "incomplete", "not_run"), ("error", "execution_error", "not_run"),
    ("empty", "incomplete", "not_run"), ("sensitive", "incomplete", "unscorable"),
    ("oversized", "completed", "unscorable"),
])
async def test_ineligible_evidence_never_calls_adapter(kind: str, execution: str, judge: str) -> None:
    evidence = raw()
    if kind == "error":
        evidence["error"] = "Controlled execution error"
    elif kind == "empty":
        evidence["turns"][0]["final_answer"] = " "
    elif kind == "sensitive":
        evidence["turns"][0]["final_answer"] = "Bearer sensitive-value"
    adapter = FakeAdapter([])
    result = (await judge_saved_evidence([case()], rubric(), [] if kind == "missing" else [evidence],
        adapter, JudgeConfig(model="fake", max_context_chars=1 if kind == "oversized" else 100000)))[0]
    assert (result.execution, result.judge) == (execution, judge)
    assert not adapter.payloads


@pytest.mark.asyncio
async def test_declared_provenance_unknown_and_duplicate_ids_rejected() -> None:
    for evidence, provenance in [([raw("foreign")], "development-exposed synthetic"),
        ([raw(), raw()], "development-exposed synthetic"), ([raw()], "production")]:
        with pytest.raises(ValueError):
            await judge_saved_evidence([case()], rubric(), evidence, None, JudgeConfig(model="fake"), provenance=provenance)


@pytest.mark.asyncio
async def test_concurrency_is_bounded_and_case_order_preserved() -> None:
    class ConcurrentAdapter:
        def __init__(self) -> None:
            self.active = 0
            self.maximum = 0

        async def judge(self, payload: dict[str, Any]) -> dict[str, Any]:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return dict(case_id=payload["scenario"]["id"], turns=[dict(turn=0, criteria=[
                dict(criterion_id="locale", status="passed", rationale="Correct locale",
                     citations=[dict(turn=0)])])])

    adapter = ConcurrentAdapter()
    cases = [case(str(index)) for index in range(5)]
    results = await judge_saved_evidence(cases, rubric(), [raw(item.id) for item in cases],
        adapter, JudgeConfig(model="fake", concurrency=2))
    assert adapter.maximum == 2
    assert [result.case_id for result in results] == [item.id for item in cases]
    assert sum(result.attempts for result in results) == 5


@pytest.mark.asyncio
async def test_completed_multiturn_requires_judgment_on_every_turn() -> None:
    scenario = case()
    scenario.turns.append("Explain?")
    evidence = raw()
    evidence["turns"].append(dict(turn=1, query="Explain?", completed=True, final_answer="Explanation."))
    result = (await judge_saved_evidence([scenario], rubric(), [evidence], FakeAdapter(["passed"]),
                                        JudgeConfig(model="fake")))[0]
    assert result.judge == "judge_error"
    assert result.error_code == "INVALID_JUDGE_OUTPUT"
    assert result.attempts == 1
