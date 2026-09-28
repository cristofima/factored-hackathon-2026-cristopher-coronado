"""Account and transaction workflow for the Foundry Responses host."""

from collections.abc import Sequence

from agent_framework import Agent, BaseChatClient, Message, Workflow
from agent_framework.orchestrations import HandoffBuilder

from app.agents.azure_chat.account_agent import AccountAgent
from app.agents.azure_chat.transaction_agent import TransactionHistoryAgent
from app.helpers.no_history_provider import NoHistoryProvider


TRIAGE_INSTRUCTIONS = """
You are a banking customer support agent triaging requests about bank accounts and transactions.
Evaluate the whole conversation and hand off to AccountAgent or TransactionHistoryAgent when the
request belongs to one of those areas.

# Triage rules
- For account information such as balances, cards, and beneficiaries, call
  handoff_to_AccountAgent.
- For banking movements and transaction history, call handoff_to_TransactionHistoryAgent.
- For payment initiation, invoice processing, or any unrelated request, explain that this
  assistant cannot help with that request.
"""


def _has_completed_agent_response(conversation: Sequence[Message]) -> bool:
    return bool(conversation) and conversation[-1].role == "assistant"


def build_hosted_workflow(
    chat_client: BaseChatClient,
    account_mcp_server_url: str,
    transaction_mcp_server_url: str,
    internal_identity_secret: str,
) -> Workflow:
    """Build the checkpoint-free workflow managed by the Responses hosting runtime."""
    triage_agent = Agent(
        client=chat_client,
        instructions=TRIAGE_INSTRUCTIONS.strip(),
        name="triage_agent",
        description="Routes banking requests to the account or transaction specialist.",
        require_per_service_call_history_persistence=True,
        context_providers=[NoHistoryProvider()],
    )
    account_agent = AccountAgent(
        chat_client,
        account_mcp_server_url,
        internal_identity_secret,
    ).build_af_agent()
    transaction_agent = TransactionHistoryAgent(
        chat_client,
        account_mcp_server_url,
        transaction_mcp_server_url,
        internal_identity_secret,
    ).build_af_agent()

    return (
        HandoffBuilder(
            name="banking_assistant_handoff",
            description="Banking account and transaction support workflow.",
            participants=[triage_agent, account_agent, transaction_agent],
            termination_condition=_has_completed_agent_response,
        )
        .with_start_agent(triage_agent)
        .build()
    )