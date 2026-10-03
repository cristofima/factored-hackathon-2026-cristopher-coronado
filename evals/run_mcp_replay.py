"""Run the production workflow with a real model and synthetic MCP sessions."""

from __future__ import annotations

import argparse
import asyncio
import base64
from contextlib import AsyncExitStack
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app" / "agent"))

from agent_framework import BaseChatClient
from agent_framework.foundry import FoundryChatClient
from azure.ai.agentserver.core import (
    FoundryAgentRequestContext, reset_request_context, set_request_context,
)
from azure.identity.aio import AzureCliCredential

from app.agents.azure_chat.hosted_workflow import build_hosted_workflow
from evals.mcp_replay import ReplayReply, ReplayServer


def evaluation_names(agent_name: str, lane: str = "mcp-replay") -> tuple[str, str]:
    name = f"{agent_name}-{lane}-eval"
    return name, f"{name} run"


def error_details(error: BaseException) -> dict[str, Any]:
    details: dict[str, Any] = {"type": type(error).__name__, "message": str(error)}
    if isinstance(error, BaseExceptionGroup):
        details["causes"] = [error_details(cause) for cause in error.exceptions]
    return details


async def run_case(
    client: BaseChatClient, case: dict[str, Any], timeout_seconds: float = 120,
) -> dict[str, Any]:
    secret = "synthetic-replay-only-not-a-production-secret"
    claims = {
        "sub": "synthetic-replay-user", "customer_id": "SYNTHETIC-CUSTOMER",
        "email": "replay@example.invalid", "locale": case.get("locale", "en"),
    }
    payload = base64.urlsafe_b64encode(json.dumps(
        claims, sort_keys=True, separators=(",", ":"),
    ).encode()).rstrip(b"=").decode()
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = set_request_context(FoundryAgentRequestContext(user_id=f"v1.{payload}.{signature}"))
    trace: list[dict[str, Any]] = []
    servers = {
        name: ReplayServer(name, [ReplayReply(**reply) for reply in case.get(name, [])], trace)
        for name in ("account", "transaction")
    }
    result: dict[str, Any] = {
        "case_id": case["id"], "offline_or_simulated": True, "lane": "mcp-replay",
        "model_execution": "caller-supplied", "expected_behavior": case["expected_behavior"],
        "query": case["query"], "locale": claims["locale"],
        "protocol_passed": False,
        "turns": [],
    }
    try:
        async with asyncio.timeout(timeout_seconds), AsyncExitStack() as stack:
            sessions = {
                name: await stack.enter_async_context(server.connect())
                for name, server in servers.items()
            }
            workflow = build_hosted_workflow(
                client, "in-memory://account", "in-memory://transaction", secret,
                account_mcp_session=sessions["account"],
                transaction_mcp_session=sessions["transaction"],
            )
            agent = workflow.as_agent(name="home_banking_agent")
            conversation = agent.create_session() if "turns" in case else None
            for turn, message in enumerate(case.get("turns", [case["query"]])):
                for server in servers.values():
                    server.turn = turn
                started = perf_counter()
                options = {"session": conversation} if conversation is not None else {}
                response = await agent.run(message, stream=True, **options).get_final_response()
                result["response"] = response.to_dict()
                result["final_answer"] = response.text
                result["turns"].append({
                    "turn": turn, "query": message, "response": response.to_dict(),
                    "final_answer": response.text, "latency_seconds": perf_counter() - started,
                })
                if not response.text.strip():
                    raise AssertionError("Workflow returned an empty final answer")
            for server in servers.values():
                server.assert_complete()
            if not response.text.strip():
                raise AssertionError("Workflow returned an empty final answer")
            result["protocol_passed"] = True
    except Exception as error:
        result["error"] = error_details(error)
    finally:
        reset_request_context(token)
    result["tool_calls"] = trace
    result["replay_failures"] = {name: server.failures for name, server in servers.items()}
    result["unconsumed_replies"] = {
        name: len(server.replies) - len([
            call for call in server.calls if "result" in call
        ]) for name, server in servers.items()
    }
    result["behavior_review"] = "pending"
    return result


async def main_async(args: argparse.Namespace) -> int:
    cases = json.loads(args.dataset.read_text(encoding="utf-8"))
    if args.case:
        cases = [case for case in cases if case["id"] in args.case]
        if {case["id"] for case in cases} != set(args.case):
            raise ValueError("Unknown replay case ID")
    if not cases or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Replay requires a nonempty dataset with unique case IDs")
    async with AzureCliCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=args.project_endpoint, model=args.model, credential=credential,
        )
        results = [await run_case(client, case, args.timeout_seconds) for case in cases]
    evaluation_name, run_name = evaluation_names(args.agent_name)
    report = {
        "evaluation_name": evaluation_name, "run_name": run_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model, "model_execution": "real", "sample_size": len(results),
        "offline_or_simulated": True, "results": results,
        "foundry_submission": "not_submitted", "behavior_review": "pending",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(results)} synthetic replay transcripts to {args.output}")
    return 0 if results and all(result["protocol_passed"] for result in results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--agent-name", default="home-banking-agent")
    parser.add_argument("--dataset", type=Path, default=ROOT / "evals" / "replay_cases.json")
    parser.add_argument("--output", type=Path, default=ROOT / "evals" / "results" / "mcp-replay.json")
    parser.add_argument("--case", action="append")
    parser.add_argument("--timeout-seconds", type=float, default=120)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())