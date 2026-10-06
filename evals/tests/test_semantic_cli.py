"""Offline CLI authorization, immutable output and budget regressions."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
import json
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

import pytest

from banking_evals.run_semantic_eval import (
    BudgetedClient, execute, parser, validate_args, write_report,
)
from banking_evals.semantic.contracts import JudgeOutput
from banking_evals.semantic.dataset import canonical_hash, load_dataset


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    path = Path(__file__).resolve().parent.parent / f".semantic-cli-test-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


@pytest.fixture
def args(tmp_path: Path) -> argparse.Namespace:
    return parser().parse_args([
        "judge", "--evidence", str(tmp_path / "capture.json"),
        "--output", str(tmp_path / "sidecar.json"),
        "--project-endpoint", "https://synthetic.example/projects/test",
        "--model", "synthetic-judge", "--authorize-model-calls", "--max-calls", "8",
    ])


def test_cli_requires_explicit_authorization(args: argparse.Namespace) -> None:
    args.authorize_model_calls = False
    with pytest.raises(ValueError, match="authorization"):
        validate_args(args)


@pytest.mark.parametrize("endpoint", [
    "http://synthetic.example", "https://user:password@synthetic.example",
    "https://synthetic.example?token=secret", "https://synthetic.example#secret",
])
def test_cli_rejects_credential_endpoints(args: argparse.Namespace, endpoint: str) -> None:
    args.project_endpoint = endpoint
    with pytest.raises(ValueError, match="endpoint"):
        validate_args(args)


@pytest.mark.parametrize(("name", "value"), [
    ("timeout_seconds", float("nan")), ("timeout_seconds", 0),
    ("max_calls", 0), ("retries", -1), ("concurrency", 0),
])
def test_cli_rejects_invalid_limits(args: argparse.Namespace, name: str, value: Any) -> None:
    setattr(args, name, value)
    with pytest.raises(ValueError, match="limits"):
        validate_args(args)


def test_cli_preserves_existing_output(args: argparse.Namespace) -> None:
    args.output.write_text("original", encoding="utf-8")
    with pytest.raises(ValueError, match="immutable"):
        validate_args(args)
    assert args.output.read_text(encoding="utf-8") == "original"


def test_cli_requires_saved_evidence(args: argparse.Namespace) -> None:
    args.evidence = None
    with pytest.raises(ValueError, match="saved evidence"):
        validate_args(args)


def test_report_creation_never_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "sidecar.json"
    write_report(path, {"foundry_submission": "not_submitted"})
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        write_report(path, {"foundry_submission": "overwritten"})
    assert path.read_bytes() == before
    assert json.loads(before)["foundry_submission"] == "not_submitted"


def test_budget_counts_each_request_without_retry() -> None:
    class Client:
        def get_response(self, *args: Any, **kwargs: Any) -> str:
            return "response"

    client = BudgetedClient(Client(), 2)
    assert client.get_response() == "response"
    assert client.get_response() == "response"
    with pytest.raises(RuntimeError, match="budget"):
        client.get_response()
    assert client.calls == 2


class _OfflineClient:
    def __init__(self, rationale: str = "Synthetic rubric judgment.") -> None:
        self.rationale = rationale
        self.payloads: list[dict[str, Any]] = []

    async def get_response(self, messages: Any = None, **kwargs: Any) -> Any:
        from types import SimpleNamespace

        if messages is None:
            return SimpleNamespace(text="Synthetic capture completion.")
        assert kwargs["options"]["response_format"] is JudgeOutput
        payload = json.loads(messages[1].text)
        self.payloads.append(payload)
        return SimpleNamespace(text=json.dumps({
            "case_id": payload["scenario"]["id"],
            "turns": [{
                "turn": turn["turn"],
                "criteria": [{
                    "criterion_id": criterion["id"], "status": "passed",
                    "rationale": self.rationale, "citations": [{"turn": turn["turn"]}],
                } for criterion in payload["rubric"]["criteria"]],
            } for turn in payload["quoted_evidence"]["turns"]],
        }))


async def _save_capture(
    args: argparse.Namespace, monkeypatch: pytest.MonkeyPatch,
    *, answer: str = "Synthetic capture completion.",
) -> dict[str, Any]:
    import sys
    from types import SimpleNamespace

    async def run_case(client: Any, case: dict[str, Any], timeout_seconds: float) -> Any:
        assert isinstance(client, BudgetedClient)
        assert timeout_seconds == args.timeout_seconds
        await client.get_response()
        calls = []
        for server in ("account", "transaction"):
            for reply in case[server]:
                calls.append(dict(reply, turn=0, server=server, sequence=len(calls)))
        return {
            "case_id": case["id"], "protocol_passed": True, "error": None,
            "turns": [{"turn": index, "query": query, "completed": True,
                       "final_answer": answer, "stream_updates": ["raw excluded"]}
                      for index, query in enumerate(case["turns"])],
            "tool_calls": calls, "response": {"raw": "excluded"},
        }

    monkeypatch.setitem(sys.modules, "banking_evals.mcp.runner", SimpleNamespace(run_case=run_case))
    args.mode, args.evidence = "capture", None
    captured = await execute(args, _OfflineClient())
    write_report(args.output, captured)
    args.mode, args.evidence = "judge", args.output
    args.output = args.output.with_name("judgment.json")
    return captured


@pytest.mark.asyncio
async def test_execute_captures_then_judges_normalized_saved_evidence(
    args: argparse.Namespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("agent_framework")
    captured = await _save_capture(args, monkeypatch)
    before = args.evidence.read_bytes()
    client = _OfflineClient()
    report = await execute(args, client)
    cases = load_dataset(args.dataset).cases
    assert captured["requested_case_ids"] == [case.id for case in cases]
    assert captured["model_calls"] == len(cases)
    assert len(client.payloads) == len(cases)
    assert report["counts"]["completed_judgments"] == len(cases)
    assert report["counts"]["technical_failures"] == 0
    assert report["foundry_submission"] == "not_submitted"
    for raw, result, payload in zip(captured["results"], report["cases"], client.payloads, strict=True):
        assert result["evidence_sha256"] == canonical_hash(raw)
        assert result["technical_checks"] == {
            "protocol_passed": True, "tool_choice": True, "task_completion": True,
        }
        assert payload["quoted_evidence"]["tool_calls"] == raw["tool_calls"]
        assert "response" not in raw
        assert all("stream_updates" not in turn for turn in raw["turns"])
    assert args.evidence.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["dataset_sha256", "rubric_sha256"])
async def test_execute_rejects_changed_capture_fingerprint_before_judging(
    args: argparse.Namespace, monkeypatch: pytest.MonkeyPatch, field: str,
) -> None:
    captured = await _save_capture(args, monkeypatch)
    captured[field] = "0" * 64
    args.evidence.write_text(json.dumps(captured), encoding="utf-8")
    client = _OfflineClient()
    with pytest.raises(ValueError, match="capture envelope"):
        await execute(args, client)
    assert client.payloads == []
    assert not args.output.exists()


@pytest.mark.asyncio
async def test_capture_rejects_sensitive_answer_without_persisting(
    args: argparse.Namespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="Sensitive evidence text"):
        await _save_capture(args, monkeypatch, answer="Bearer synthetic-sensitive-canary")
    assert not args.output.exists()


@pytest.mark.asyncio
async def test_execute_rejects_sensitive_saved_answer_before_judging(
    args: argparse.Namespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = await _save_capture(args, monkeypatch)
    captured["results"][0]["turns"][0]["final_answer"] = "Bearer synthetic-sensitive-canary"
    args.evidence.write_text(json.dumps(captured), encoding="utf-8")
    client = _OfflineClient()
    with pytest.raises(ValueError, match="Sensitive evidence text"):
        await execute(args, client)
    assert client.payloads == []
    assert not args.output.exists()


@pytest.mark.asyncio
async def test_execute_rejects_sensitive_judgment_without_echoing_output(
    args: argparse.Namespace, monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("agent_framework")
    await _save_capture(args, monkeypatch)
    client = _OfflineClient("Bearer synthetic-sensitive-canary")
    report = await execute(args, client)
    assert len(client.payloads) == report["counts"]["requested_cases"]
    assert report["counts"]["completed_judgments"] == 0
    assert all(case["error_code"] == "INVALID_JUDGE_OUTPUT" for case in report["cases"])
    assert all(case["judgment"] is None for case in report["cases"])
    assert "synthetic-sensitive-canary" not in json.dumps(report)


@pytest.mark.asyncio
async def test_budget_intercepts_actual_framework_agent_requests_without_network() -> None:
    framework = pytest.importorskip("agent_framework")

    class Client(framework.BaseChatClient):
        def __init__(self) -> None:
            super().__init__()
            self.requests = 0

        async def _inner_get_response(
            self, *, messages: Any, stream: bool, options: Any, **kwargs: Any,
        ) -> Any:
            assert stream is False
            self.requests += 1
            return framework.ChatResponse(messages=[framework.Message("assistant", ["Offline."])])

    transport = Client()
    budgeted = BudgetedClient(transport, 1)
    agent = framework.Agent(client=budgeted, name="offline-budget-check")
    response = await agent.run("Synthetic request.")
    assert response.text == "Offline."
    assert (budgeted.calls, transport.requests) == (1, 1)
    with pytest.raises(RuntimeError, match="budget"):
        await agent.run("Second synthetic request.")
    assert (budgeted.calls, transport.requests) == (1, 1)
