"""Give each hosted workflow request independent mutable executor state."""

from collections.abc import AsyncIterator, Callable
from contextvars import ContextVar
from typing import Any

from agent_framework import WorkflowAgent
from agent_framework_foundry_hosting import ResponsesHostServer


class IsolatedResponsesHostServer(ResponsesHostServer):
    def __init__(self, agent_factory: Callable[[], WorkflowAgent]) -> None:
        self._agent_factory = agent_factory
        self._request_agent: ContextVar[WorkflowAgent | None] = ContextVar(
            "responses_request_workflow", default=None,
        )
        super().__init__(agent_factory())

    @property
    def _agent(self) -> WorkflowAgent:
        return self._request_agent.get() or self._template_agent

    @_agent.setter
    def _agent(self, agent: WorkflowAgent) -> None:
        self._template_agent = agent

    async def _handle_inner_workflow(
        self, *args: Any, **kwargs: Any,
    ) -> AsyncIterator[Any]:
        token = self._request_agent.set(self._agent_factory())
        try:
            async for event in super()._handle_inner_workflow(*args, **kwargs):
                yield event
        finally:
            self._request_agent.reset(token)