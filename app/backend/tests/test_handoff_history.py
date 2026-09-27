"""Regression test for the handoff participants' history configuration."""

from unittest.mock import AsyncMock

import pytest
from agent_framework import InMemoryCheckpointStorage, MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatCompletionClient

from app.agents.azure_chat.account_agent import AccountAgent
from app.agents.azure_chat.handoff_orchestrator import HandoffOrchestrator
from app.agents.azure_chat.payment_agent import PaymentAgent
from app.agents.azure_chat.transaction_agent import TransactionHistoryAgent


@pytest.mark.asyncio
async def test_handoff_builds_with_per_service_call_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MCPStreamableHTTPTool, "connect", AsyncMock())
    client = OpenAIChatCompletionClient(
        model="test-model", api_key="test-key", base_url="http://localhost:1"
    )
    orchestrator = HandoffOrchestrator(
        azure_chat_client=client,
        account_agent=AccountAgent(client, "http://localhost:8070/mcp"),
        transaction_agent=TransactionHistoryAgent(
            client, "http://localhost:8070/mcp", "http://localhost:8071/mcp"
        ),
        payment_agent=PaymentAgent(
            client,
            "http://localhost:8070/mcp",
            "http://localhost:8071/mcp",
            "http://localhost:8072/mcp",
        ),
    )

    await orchestrator.initialize(InMemoryCheckpointStorage())

    assert orchestrator.workflow is not None