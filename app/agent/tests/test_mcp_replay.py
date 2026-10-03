"""Offline protocol checks, not model-quality or live authorization evidence."""

import json
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import MCPStreamableHTTPTool

from app.agents.azure_chat.hosted_workflow import build_hosted_workflow
from evals.mcp_replay import ReplayReply, ReplayServer, load_contracts
from evals.run_mcp_replay import evaluation_names, run_case


async def test_replay_discovers_contracts_and_executes_without_http() -> None:
    replay = ReplayServer("account", [ReplayReply(
        "getAccountDetails", {"product_number": "SYNTHETIC-001"},
        {"accountNumber": "SYNTHETIC-001", "balance": 12, "currency": "USD"},
    )])
    async with replay.connect() as session:
        tools = await session.list_tools()
        contract = next(item for item in tools.tools if item.name == "getAccountDetails")
        assert contract.description == "Get account details and available payment methods"
        assert contract.inputSchema["required"] == ["product_number"]
        assert "headers" not in contract.inputSchema["properties"]
        async with MCPStreamableHTTPTool(
            name="Account MCP server client", url="in-memory://account", session=session,
            load_prompts=False,
        ) as client:
            assert any(item.name == "getAccountDetails" for item in client.functions)
            result = await session.call_tool("getAccountDetails", {"product_number": "SYNTHETIC-001"})
            assert not result.isError
            assert json.loads(result.content[0].text)["balance"] == 12
    replay.assert_complete()


async def test_replay_propagates_errors_and_rejects_unexpected_calls() -> None:
    replay = ReplayServer("account", [ReplayReply(
        "getAccountDetails", {"product_number": "FOREIGN"},
        error="Account does not belong to the authenticated customer",
    )])
    async with replay.connect() as session:
        denied = await session.call_tool("getAccountDetails", {"product_number": "FOREIGN"})
        assert denied.isError
        replay.assert_complete()
        unexpected = await session.call_tool("getAccountsByUserName", {"userName": "other"})
        assert unexpected.isError
    with pytest.raises(AssertionError, match="Unexpected replay call"):
        replay.assert_complete()


async def test_replay_instances_and_server_contracts_are_isolated() -> None:
    first = ReplayServer("transaction", [ReplayReply("listSupportCases", {}, [])])
    second = ReplayServer("transaction", [ReplayReply("listSupportCases", {}, [{"id": "CASE"}])])
    async with first.connect() as first_session, second.connect() as second_session:
        assert (await first_session.call_tool("listSupportCases", {})).content[0].text == "[]"
        assert (await second_session.call_tool("listSupportCases", {})).content[0].text != "[]"
    first.assert_complete()
    second.assert_complete()
    assert "getAccountDetails" not in {item.name for item in load_contracts("transaction")}


async def test_workflow_passes_injected_sessions_to_all_mcp_clients() -> None:
    account = ReplayServer("account", [])
    transaction = ReplayServer("transaction", [])
    async with account.connect() as account_session, transaction.connect() as transaction_session:
        with patch("app.agents.azure_chat.account_agent.MCPStreamableHTTPTool") as account_tool:
            with patch("app.agents.azure_chat.transaction_agent.MCPStreamableHTTPTool") as transaction_tool:
                account_tool.return_value = MCPStreamableHTTPTool(
                    name="account", url="in-memory://account", session=account_session,
                )
                transaction_tool.return_value = MCPStreamableHTTPTool(
                    name="transaction", url="in-memory://transaction", session=transaction_session,
                )
                build_hosted_workflow(
                    MagicMock(), "in-memory://account", "in-memory://transaction",
                    "test-secret-key-with-at-least-32-bytes",
                    account_mcp_session=account_session, transaction_mcp_session=transaction_session,
                )
        assert account_tool.call_args.kwargs["session"] is account_session
        assert transaction_tool.call_args_list[0].kwargs["session"] is account_session
        assert transaction_tool.call_args_list[1].kwargs["session"] is transaction_session


def test_evaluation_names_follow_agent_first_reference_convention() -> None:
    assert evaluation_names("home-banking-agent") == (
        "home-banking-agent-mcp-replay-eval", "home-banking-agent-mcp-replay-eval run",
    )


async def test_runner_preserves_signed_identity_and_records_failures() -> None:
    from azure.ai.agentserver.core import get_request_context
    from app.common.internal_identity import get_internal_principal

    def fail_workflow(*args: object, **kwargs: object) -> None:
        principal = get_internal_principal("synthetic-replay-only-not-a-production-secret")
        assert principal.locale == "es"
        assert principal.customer_id == "SYNTHETIC-CUSTOMER"
        raise RuntimeError("controlled model failure")

    original_context = get_request_context()
    with patch("evals.run_mcp_replay.build_hosted_workflow", side_effect=fail_workflow):
        result = await run_case(MagicMock(), {
            "id": "failure", "locale": "es", "query": "test", "expected_behavior": "test",
        })
    assert not result["protocol_passed"]
    assert result["error"]["type"] == "ExceptionGroup"
    cause = result["error"]
    while "causes" in cause:
        assert len(cause["causes"]) == 1
        cause = cause["causes"][0]
    assert cause == {"type": "RuntimeError", "message": "controlled model failure"}
    assert result["behavior_review"] == "pending"
    assert get_request_context() is original_context


async def test_runner_records_full_transcript_and_interleaved_tools() -> None:
    from unittest.mock import AsyncMock

    text = "Complete synthetic answer. " * 30
    response = MagicMock(text=text)
    response.to_dict.return_value = {"messages": [{"text": text}]}

    async def final_response() -> object:
        await transaction_session.call_tool("getLastTransactions", {"product_number": "TEST"})
        await account_session.call_tool("getAccountDetails", {"product_number": "TEST"})
        return response

    def build_workflow(*args: object, **kwargs: object) -> MagicMock:
        nonlocal account_session, transaction_session
        account_session = kwargs["account_mcp_session"]
        transaction_session = kwargs["transaction_mcp_session"]
        workflow = MagicMock()
        workflow.as_agent.return_value.run.return_value.get_final_response = AsyncMock(
            side_effect=final_response,
        )
        return workflow

    account_session = None
    transaction_session = None
    with patch("evals.run_mcp_replay.build_hosted_workflow", side_effect=build_workflow):
        result = await run_case(MagicMock(), {
            "id": "success", "query": "test", "expected_behavior": "test",
            "account": [{"tool": "getAccountDetails", "arguments": {"product_number": "TEST"}, "result": {}}],
            "transaction": [{"tool": "getLastTransactions", "arguments": {"product_number": "TEST"}, "result": []}],
        })
    assert result["protocol_passed"]
    assert result["final_answer"] == text
    assert result["response"]["messages"][0]["text"] == text
    assert [call["server"] for call in result["tool_calls"]] == ["transaction", "account"]
    assert [call["sequence"] for call in result["tool_calls"]] == [0, 1]


def test_replay_fixtures_match_public_tool_arguments() -> None:
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).resolve().parents[3] / "evals/replay_cases.json").read_text())
    for case in cases:
        for server in ("account", "transaction"):
            contracts = {tool.name: tool.inputSchema for tool in load_contracts(server)}
            for reply in case.get(server, []):
                assert set(reply["arguments"]) == set(contracts[reply["tool"]]["properties"])