"""Tests for the Responses-hosted banking workflow."""

from unittest.mock import MagicMock

from agent_framework import Message
from agent_framework_foundry_hosting import ResponsesHostServer

from app.agents.azure_chat.hosted_workflow import (
    _has_completed_agent_response,
    build_hosted_workflow,
)


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