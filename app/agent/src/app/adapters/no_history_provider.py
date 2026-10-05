"""No-op context provider that prevents InMemoryHistoryProvider auto-injection.

The Agent Framework auto-injects an InMemoryHistoryProvider when an agent has
no context_providers set.  Inside a HandoffBuilder workflow the executor
already manages the full conversation history, so the auto-injected provider
causes message duplication that grows each turn.

Assigning this provider to agents participating in a handoff workflow
disables the auto-injection without altering the agent's behaviour.
"""

from typing import Any

from agent_framework import AgentSession, ContextProvider, SessionContext


class NoHistoryProvider(ContextProvider):
    """A no-op context provider whose only purpose is to exist."""

    def __init__(self) -> None:
        super().__init__("no_history_provider")

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:  # noqa: D401
        pass
