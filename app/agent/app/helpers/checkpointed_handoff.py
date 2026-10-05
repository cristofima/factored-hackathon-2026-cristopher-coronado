"""Synchronize fresh Responses inputs when restarting a checkpointed handoff."""

from __future__ import annotations

from typing import Any

from agent_framework import Agent, Message, WorkflowContext, handler
from agent_framework.orchestrations import (
    HandoffAgentExecutor,
    HandoffBuilder,
    HandoffConfiguration,
)


class _CheckpointedStartExecutor(HandoffAgentExecutor):
    @handler
    async def from_messages(
        self,
        messages: list[str | Message],
        ctx: WorkflowContext[Any, Any],
    ) -> None:
        # The SDK broadcasts first input and request_info replies, but not fresh
        # Responses turns restored onto an already-completed conversation.
        if self._full_conversation:
            normalized = [
                Message(role="user", text=message) if isinstance(message, str) else message
                for message in messages
            ]
            await self._broadcast_messages(normalized, ctx)
        await super().from_messages(messages, ctx)


class CheckpointedHandoffBuilder(HandoffBuilder):
    """Keep SDK routing/checkpoints with a fresh-input-aware start executor.

    This narrow protected builder hook is covered through the installed SDK's
    actual Responses handler; remove it when upstream broadcasts fresh turns.
    """

    def _resolve_executors(
        self,
        agents: dict[str, Agent],
        handoffs: dict[str, list[HandoffConfiguration]],
    ) -> dict[str, HandoffAgentExecutor]:
        executors = super()._resolve_executors(agents, handoffs)
        start_id = self._start_id
        if start_id is None:
            raise ValueError("A checkpointed handoff requires a start agent")
        if self._autonomous_mode:
            raise ValueError("Checkpointed banking handoffs do not support autonomous mode")
        executors[start_id] = _CheckpointedStartExecutor(
            agent=agents[start_id],
            handoffs=handoffs.get(start_id, []),
            is_start_agent=True,
            termination_condition=self._termination_condition,
        )
        return executors
