"""Tests for the Responses-hosted banking workflow."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_framework import (
    Agent, AgentContext, AgentResponse, AgentResponseUpdate, AgentSession, BaseChatClient, ChatResponse,
    ChatResponseUpdate, Content, Message, ResponseStream, WorkflowAgent, tool,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import HandoffBuilder
from agent_framework_foundry_hosting import ResponsesHostServer
from agent_framework.exceptions import ToolExecutionException

from app.agents.azure_chat.hosted_workflow import (
    _has_completed_agent_response,
    build_hosted_workflow,
)
from app.agents.azure_chat.transaction_agent import TransactionHistoryAgent
from app.helpers.no_history_provider import NoHistoryProvider
from app.helpers.handoff_middleware import HandoffNarrationMiddleware
from app.helpers.tool_error_middleware import OwnershipErrorMiddleware
from app.helpers.isolated_responses_host import IsolatedResponsesHostServer
from app.helpers.user_profile_provider import UserProfileProvider


def test_transaction_instructions_scope_new_disputes_to_cards() -> None:
    instructions = " ".join(TransactionHistoryAgent.instructions.split())
    assert "only for Debit Card and Credit Card transactions, not bank account transactions" in instructions
    assert "Verify the product type before reporting a dispute" in instructions
    assert "Never infer a card-to-account relationship" in instructions
    assert "Existing support cases remain available" in instructions


@pytest.mark.parametrize("denied", [False, True])
@pytest.mark.parametrize("narrated", [False, True])
async def test_foundry_function_loop_handoff_queries_account_and_finishes(
    denied: bool, narrated: bool,
) -> None:
    lookup_numbers: list[str] = []
    model_results: list[str] = []

    @tool(name="getAccountDetails")
    def lookup(product_number: str) -> str:
        lookup_numbers.append(product_number)
        if denied:
            raise ToolExecutionException("Account does not belong to the authenticated customer")
        return "Account number: ACCOUNT-NUMBER; balance: USD 12.00"

    client = FoundryChatClient(
        project_endpoint="https://example.services.ai.azure.com/api/projects/test",
        model="test-model", credential=MagicMock(),
    )
    model_calls = 0

    def model_response(*args: object, **kwargs: object) -> ResponseStream:
        nonlocal model_calls
        model_calls += 1
        call_number = (model_calls - 1) % 3 + 1

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            if call_number == 1:
                contents = [
                    Content.from_function_call("handoff", "handoff_to_AccountAgent", arguments="{}"),
                ]
                if narrated:
                    contents.insert(0, Content(
                        type="text", text="Transferring you to the account specialist."
                    ))
            elif call_number == 2:
                contents = [Content.from_function_call(
                    "lookup", "getAccountDetails", arguments='{"product_number":"ACCOUNT-NUMBER"}'
                )]
            else:
                for message in kwargs["messages"]:
                    for content in message.contents:
                        if content.type == "function_result":
                            model_results.append(str(content.result))
                contents = [Content(type="text", text=(
                    "The requested account is unavailable." if denied else "Your balance is USD 12.00."
                ))]
            yield ChatResponseUpdate(role="assistant", contents=contents)

        return ResponseStream(updates(), finalizer=ChatResponse.from_updates)

    triage = Agent(client=client, name="triage_agent", context_providers=[NoHistoryProvider()],
                   require_per_service_call_history_persistence=True,
                   middleware=[HandoffNarrationMiddleware()])
    specialist = Agent(client=client, name="AccountAgent", tools=[lookup],
                       require_per_service_call_history_persistence=True,
                       context_providers=[NoHistoryProvider()],
                       middleware=[OwnershipErrorMiddleware()])
    workflow = HandoffBuilder(
        participants=[triage, specialist], termination_condition=_has_completed_agent_response,
    ).with_start_agent(triage).add_handoff(triage, [specialist]).build()

    with patch.object(client, "_inner_get_response", model_response):
        events = [event async for event in workflow.run([
            Message(role="user", contents=["Show my previous account"]),
            Message(role="assistant", contents=["Your previous balance is USD 12.00."],
                    author_name="AccountAgent"),
            Message(role="user", contents=["Show my account"]),
        ], stream=True)]

    assert lookup_numbers == ["ACCOUNT-NUMBER"]
    assert model_calls == 3
    assert any(event.type == "output" and event.data.text == (
        "The requested account is unavailable." if denied else "Your balance is USD 12.00."
    ) for event in events)
    assert not any(event.type == "request_info" for event in events)
    assert any("ACCESS_DENIED" in result for result in model_results) == denied

    def create_agent() -> WorkflowAgent:
        return HandoffBuilder(
            participants=[triage, specialist], termination_condition=_has_completed_agent_response,
        ).with_start_agent(triage).add_handoff(triage, [specialist]).build().as_agent(
            name="home_banking_agent",
        )

    host = IsolatedResponsesHostServer(create_agent)

    async def run_request(
        server: ResponsesHostServer, *args: Any, **kwargs: Any,
    ) -> AsyncIterator[AgentResponse]:
        yield await server._agent.run(
            "Show a different account", session=AgentSession(), stream=True,
        ).get_final_response()

    with patch.object(client, "_inner_get_response", model_response):
        with patch.object(ResponsesHostServer, "_handle_inner_workflow", run_request):
            responses = [response async for response in host._handle_inner_workflow()]

    assert lookup_numbers == ["ACCOUNT-NUMBER", "ACCOUNT-NUMBER"]
    response = responses[0]
    assert response.text == (
        "The requested account is unavailable." if denied else "Your balance is USD 12.00."
    )


async def test_host_isolates_concurrent_workflow_requests() -> None:
    def create_agent() -> WorkflowAgent:
        return build_hosted_workflow(
            MagicMock(), "http://127.0.0.1:1/mcp", "http://127.0.0.1:2/mcp",
            "test-secret-key-with-at-least-32-bytes",
        ).as_agent(name="home_banking_agent")

    host = IsolatedResponsesHostServer(create_agent)
    template = host._agent
    request_agents: list[WorkflowAgent] = []
    both_started = asyncio.Event()

    async def handle_request(
        server: ResponsesHostServer, *args: Any, **kwargs: Any,
    ) -> AsyncIterator[WorkflowAgent]:
        request_agents.append(server._agent)
        if len(request_agents) == 2:
            both_started.set()
        await both_started.wait()
        yield server._agent

    async def consume() -> list[WorkflowAgent]:
        return [agent async for agent in host._handle_inner_workflow()]

    with patch.object(ResponsesHostServer, "_handle_inner_workflow", handle_request):
        results = await asyncio.gather(consume(), consume())

    assert results == [[request_agents[0]], [request_agents[1]]]
    assert request_agents[0].workflow is not request_agents[1].workflow
    assert all(agent is not template for agent in request_agents)
    assert host._agent is template


@pytest.mark.parametrize("stream", [False, True])
async def test_handoff_middleware_preserves_triage_final_answer(stream: bool) -> None:
    expected = "I can help with account and transaction inquiries."
    context = AgentContext(agent=MagicMock(), messages=[], stream=stream)

    async def updates() -> AsyncIterator[AgentResponseUpdate]:
        yield AgentResponseUpdate(role="assistant", contents=[Content(type="text", text=expected)])

    context.result = (
        ResponseStream(updates(), finalizer=AgentResponse.from_updates) if stream
        else AgentResponse(messages=[Message(role="assistant", contents=[expected])])
    )

    await HandoffNarrationMiddleware().process(context, AsyncMock())

    response = await context.result.get_final_response() if stream else context.result
    assert response.text == expected
    assert _has_completed_agent_response(response.messages)


async def test_ownership_error_is_safe_and_operational_errors_are_not_denials() -> None:
    context = MagicMock()
    middleware = OwnershipErrorMiddleware()
    failure = AsyncMock(side_effect=ToolExecutionException(
        "Error calling tool 'getAccountDetails': "
        "Account does not belong to the authenticated customer"
    ))

    await middleware.process(context, failure)

    assert context.result.startswith("Error: ACCESS_DENIED.")
    failure.assert_awaited_once()
    with pytest.raises(ToolExecutionException, match="connection lost"):
        await middleware.process(
            context, AsyncMock(side_effect=ToolExecutionException("connection lost"))
        )


async def test_streaming_handoff_emits_specialist_response() -> None:
    async def updates(agent_name: str) -> AsyncIterator[AgentResponseUpdate]:
        if agent_name == "triage_agent":
            yield AgentResponseUpdate(role="assistant", author_name=agent_name, contents=[
                Content(type="text", text="Transferring you to the account specialist."),
                Content.from_function_call("handoff-call", "handoff_to_AccountAgent", arguments="{}"),
            ])
            yield AgentResponseUpdate(role="tool", author_name=agent_name, contents=[
                Content(type="function_result", call_id="handoff-call",
                        result={"handoff_to": "AccountAgent"}),
            ])
        else:
            yield AgentResponseUpdate(role="assistant", author_name=agent_name, contents=[
                Content(type="text", text="The requested account is unavailable."),
            ])

    def run_agent(agent: Agent, *args: object, **kwargs: object) -> ResponseStream:
        async def sanitized_updates() -> AsyncIterator[AgentResponseUpdate]:
            context = AgentContext(agent=agent, messages=[], stream=True)
            context.result = ResponseStream(updates(agent.name), finalizer=AgentResponse.from_updates)
            await HandoffNarrationMiddleware().process(context, AsyncMock())
            async for update in context.result:
                yield update

        return ResponseStream(sanitized_updates(), finalizer=AgentResponse.from_updates)

    participants = [
        Agent(client=MagicMock(), name=name,
              require_per_service_call_history_persistence=True,
              context_providers=[NoHistoryProvider()])
        for name in ("triage_agent", "AccountAgent")
    ]
    workflow = HandoffBuilder(
        participants=participants,
        termination_condition=_has_completed_agent_response,
    ).with_start_agent(participants[0]).build()

    with patch.object(Agent, "run", run_agent):
        events = [event async for event in workflow.run("Show account details", stream=True)]

    assert any(
        event.type == "output" and event.data.author_name == "AccountAgent"
        and event.data.text == "The requested account is unavailable."
        for event in events
    )


async def test_handoff_reaches_specialist_before_terminating() -> None:
    client = MagicMock(spec=BaseChatClient)
    client.get_response = AsyncMock(
        side_effect=[
            ChatResponse(messages=[
                Message(role="assistant", contents=[
                    Content.from_function_call(
                        "handoff-call", "handoff_to_AccountAgent", arguments="{}"
                    ),
                ], author_name="triage_agent"),
                Message(role="tool", contents=[Content(
                    type="function_result",
                    call_id="handoff-call",
                    result={"handoff_to": "AccountAgent"},
                )]),
            ]),
            ChatResponse(messages=[Message(role="assistant", contents=[
                "The requested account is unavailable.",
            ], author_name="AccountAgent")]),
        ]
    )
    participants = [
        Agent(
            client=client,
            name=name,
            require_per_service_call_history_persistence=True,
            context_providers=[NoHistoryProvider()],
        )
        for name in ("triage_agent", "AccountAgent")
    ]
    workflow = HandoffBuilder(
        participants=participants,
        termination_condition=_has_completed_agent_response,
    ).with_start_agent(participants[0]).build()

    await workflow.run("Show details for the requested account")

    assert client.get_response.call_count == 2


def test_tool_only_or_empty_assistant_message_does_not_complete_turn() -> None:
    for contents in (
        [],
        ["   "],
        [Content.from_function_call("handoff-call", "handoff_to_AccountAgent", arguments="{}")],
    ):
        assert not _has_completed_agent_response([Message(role="assistant", contents=contents)])


def test_has_completed_agent_response_requires_assistant_message() -> None:
    conversation = [Message(role="user", contents=["What is my balance?"])]

    assert not _has_completed_agent_response(conversation)

    conversation.append(
        Message(
            role="assistant",
            contents=["Your balance is EUR 10,000."],
            author_name="AccountAgent",
        )
    )

    assert _has_completed_agent_response(conversation)


def test_build_hosted_workflow_without_mcp_connections() -> None:
    """The hosted workflow must not connect to MCP services during process startup."""
    workflow = build_hosted_workflow(
        MagicMock(),
        "http://127.0.0.1:1/mcp",
        "http://127.0.0.1:2/mcp",
        "test-secret-key-with-at-least-32-bytes",
    )

    agent = workflow.as_agent(name="home_banking_agent")
    server = ResponsesHostServer(agent)

    assert workflow.name == "banking_assistant_handoff"
    assert server is not None


def test_all_workflow_participants_receive_verified_profile_context() -> None:
    with patch("app.agents.azure_chat.hosted_workflow.HandoffBuilder") as builder:
        build_hosted_workflow(MagicMock(), "http://127.0.0.1:1/mcp",
                              "http://127.0.0.1:2/mcp", "test-secret")
    participants = builder.call_args.kwargs["participants"]
    assert {agent.name for agent in participants} == {
        "triage_agent", "AccountAgent", "TransactionHistoryAgent",
    }
    for agent in participants:
        assert sum(isinstance(provider, UserProfileProvider)
                   for provider in agent.context_providers) == 1