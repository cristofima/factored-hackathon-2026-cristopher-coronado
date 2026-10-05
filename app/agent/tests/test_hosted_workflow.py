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
    TRIAGE_INSTRUCTIONS,
    _has_completed_agent_response,
    build_hosted_workflow,
)
from app.agents.azure_chat.account_agent import AccountAgent
from app.agents.azure_chat.transaction_agent import TransactionHistoryAgent
from app.adapters.no_history_provider import NoHistoryProvider
from app.adapters.handoff_middleware import HandoffNarrationMiddleware
from app.adapters.tool_error_middleware import OwnershipErrorMiddleware
from app.adapters.isolated_responses_host import IsolatedResponsesHostServer
from app.context.user_profile_provider import UserProfileProvider


def test_supplied_number_inquiries_use_direct_owned_resource_tools() -> None:
    account = " ".join(AccountAgent.instructions.split())
    transactions = " ".join(TransactionHistoryAgent.instructions.split())
    assert "call getAccountDetails directly with that number" in account
    assert "Do not first call getAccountsByUserName" in account
    assert "rely on the tool's ownership check" in account
    assert "call getLastTransactions directly with that number" in transactions
    assert "Do not first call getAccountDetails or getAccountsByUserName" in transactions
    assert "the movement tool checks ownership" in transactions


def test_transaction_instructions_scope_new_disputes_to_cards() -> None:
    instructions = " ".join(TransactionHistoryAgent.instructions.split())
    assert "only for Debit Card and Credit Card transactions, not bank account transactions" in instructions
    assert "Verify the product type before reporting a dispute" in instructions
    assert "Never infer a card-to-account relationship" in instructions
    assert "Existing support cases remain available" in instructions


@pytest.mark.parametrize("requirement", [
    "getLastTransactions returns only the latest five movements",
    "it has no date or pagination arguments",
    "Never require a memorized transaction ID",
    "never masked digits or product IDs",
    "Ask only the missing discriminating question",
    "Show at most five tool-backed candidates",
    "Resolve multiple matches explicitly",
    "never select the first or newest match by assumption",
    "mention limited coverage",
    "Confirm the selected readable charge",
    "preserve an expected amount in the reason",
    "Identification confirmation is not consent",
    "Unclear consent requires clarification, not a tool call",
    "a decline is not an invalid verdict",
    "never a runtime compensation movement",
    "DISPUTE_ALREADY_ACTIVE",
    "if no unique match exists ask for selection",
    "Do not expose raw exception details",
])
def test_dispute_discovery_instruction_contract(requirement: str) -> None:
    instructions = " ".join(TransactionHistoryAgent.instructions.split())
    assert requirement in instructions


@pytest.mark.parametrize("requirement", [
    "Only after a successful tool response/readback present an intake receipt",
    "does not block a card, refund, post a movement or change a balance",
    "Stored fraud scores are synthetic routing signals only",
    "Assigned operators can record reasoned verdicts",
    "RESOLVED_INVALID records an invalid verdict without compensation",
    "PENDING_EFFECTS means a valid verdict is recorded",
    "only with recorded financialEffectsStatus and effects movement evidence",
    "Credit-card adjustments reduce debt",
    "never external processor enforcement or an automatic block",
    "Do not reveal staff-only evidence",
    "Manual-created cases are available through the same persisted tools",
    "consent is not evidence that an operator investigated",
])
def test_dispute_receipt_instruction_contract(requirement: str) -> None:
    instructions = " ".join(TransactionHistoryAgent.instructions.split())
    assert requirement in instructions
    assert "Operator adjudication is not yet implemented" not in instructions
    assert "balance change is implemented" not in instructions
    assert "investigation was authorized" not in instructions


@pytest.mark.parametrize("requirement", [
    "previewTransactionDispute",
    "Never display previewToken",
    "Only after explicit consent call reportTransactionDispute",
    "recoverTransactionDispute",
    "never call reportTransactionDispute again or ask for second consent",
    "An application decline creates no case and must not trigger a mutation",
])
def test_pre_intake_consent_instruction_contract(requirement: str) -> None:
    instructions = " ".join(TransactionHistoryAgent.instructions.split())
    assert requirement in instructions


def test_dispute_consultation_instruction_contract() -> None:
    triage = " ".join(TRIAGE_INSTRUCTIONS.split())
    instructions = " ".join(TransactionHistoryAgent.instructions.split())
    assert "case status, timelines, and follow-up questions about a dispute" in triage
    assert "handoff_to_TransactionHistoryAgent" in triage
    assert "Existing-case consultations are read-only" in instructions
    assert "never guess an ID or select the newest case" in instructions
    assert "getSupportCase again on each status follow-up" in instructions
    assert "getSupportCaseTimeline for event questions" in instructions
    assert "report an empty result as no available cases" in instructions
    assert "do not reveal whether another customer owns it" in instructions
    assert "not that an operator has taken over or issued a verdict" in instructions


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


@pytest.mark.parametrize("decision", ["accept", "decline", "unclear", "rest-accepted"])
async def test_dispute_sdk_continuation_preserves_proposal_and_receipt(decision: str) -> None:
    calls: list[tuple[str, str]] = []

    @tool(name="previewTransactionDispute")
    def preview(transaction_id: str, reason: str) -> str:
        calls.append(("preview", transaction_id))
        return '{"previewToken":"synthetic-preview","transactionId":"tx-1"}'

    @tool(name="reportTransactionDispute")
    def accept(preview_token: str) -> str:
        calls.append(("accept", preview_token))
        return '{"caseId":"CASE-1","status":"IN_REVIEW"}'

    @tool(name="getSupportCase")
    def read_case(case_id: str) -> str:
        calls.append(("read", case_id))
        return '{"caseId":"CASE-1","status":"IN_REVIEW"}'

    client = FoundryChatClient(
        project_endpoint="https://example.services.ai.azure.com/api/projects/test",
        model="test-model", credential=MagicMock(),
    )
    phase = "preview"
    model_calls = 0
    results: list[str] = []

    def model_response(*args: object, **kwargs: object) -> ResponseStream:
        nonlocal model_calls
        model_calls += 1

        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            for message in kwargs["messages"]:
                for content in message.contents:
                    if content.type == "function_result":
                        results.append(str(content.result))
            if phase == "preview" and model_calls == 1:
                contents = [Content.from_function_call(
                    "preview-1", "previewTransactionDispute",
                    arguments='{"transaction_id":"tx-1","reason":"Unrecognized purchase"}',
                )]
            elif phase == "decision" and model_calls == 1 and decision in ("accept", "rest-accepted"):
                contents = [Content.from_function_call(
                    "decision-1", "reportTransactionDispute" if decision == "accept" else "getSupportCase",
                    arguments='{"preview_token":"synthetic-preview"}' if decision == "accept"
                    else '{"case_id":"CASE-1"}',
                )]
            else:
                text = "May I create this dispute and send it for review?"
                if phase == "decision":
                    text = (
                        "Case CASE-1 is in review." if decision in ("accept", "rest-accepted")
                        else "No case was created." if decision == "decline"
                        else "Please clarify whether you consent to creation."
                    )
                contents = [Content(type="text", text=text)]
            yield ChatResponseUpdate(role="assistant", contents=contents)

        return ResponseStream(updates(), finalizer=ChatResponse.from_updates)

    specialist = Agent(
        client=client, name="TransactionAgent", instructions=TransactionHistoryAgent.instructions,
        tools=[preview, accept, read_case],
    )
    session = AgentSession()
    with patch.object(client, "_inner_get_response", model_response):
        proposal = await specialist.run(
            "Report this charge", session=session, stream=True,
        ).get_final_response()
        assert calls == [("preview", "tx-1")]
        assert "CASE-" not in proposal.text
        assert "synthetic-preview" not in proposal.text
        assert any("synthetic-preview" in result for result in results)
        phase = "decision"
        model_calls = 0
        receipt = await specialist.run({
            "accept": "I consent to creating the proposed dispute.",
            "decline": "Do not create it.",
            "unclear": "Yes, that is the charge.",
            "rest-accepted": "The application recorded CASE-1; acknowledge the receipt.",
        }[decision], session=session, stream=True).get_final_response()

    expected = [("preview", "tx-1")]
    if decision == "accept":
        expected.append(("accept", "synthetic-preview"))
    elif decision == "rest-accepted":
        expected.append(("read", "CASE-1"))
    assert calls == expected
    assert ("CASE-1" in receipt.text) == (decision in ("accept", "rest-accepted"))
    assert "synthetic-preview" not in receipt.text


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