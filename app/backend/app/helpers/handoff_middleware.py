"""Keep handoff narration out of the workflow's completion history."""

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

from agent_framework import (
    AgentContext, AgentMiddleware, AgentResponse, AgentResponseUpdate, ResponseStream,
)


def _remove_handoff_narration(response: AgentResponse) -> AgentResponse:
    has_handoff = any(
        content.type == "function_call"
        and content.name
        and content.name.startswith("handoff_to_")
        for message in response.messages
        for content in message.contents
    )
    if has_handoff:
        for message in response.messages:
            message.contents = [content for content in message.contents if content.type != "text"]
    return response


class HandoffNarrationMiddleware(AgentMiddleware):
    async def process(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        await call_next()
        result = context.result
        if isinstance(result, AgentResponse):
            context.result = _remove_handoff_narration(result)
        elif isinstance(result, ResponseStream):
            async def updates() -> AsyncIterator[AgentResponseUpdate]:
                buffered = [update async for update in result]
                response = await result.get_final_response()
                has_handoff = any(
                    content.type == "function_call"
                    and content.name
                    and content.name.startswith("handoff_to_")
                    for update in buffered for content in update.contents
                )
                _remove_handoff_narration(response)
                for update in buffered:
                    if has_handoff:
                        update.contents = [
                            content for content in update.contents if content.type != "text"
                        ]
                    yield update

            async def finalize(
                _buffered: Sequence[AgentResponseUpdate],
            ) -> AgentResponse:
                return _remove_handoff_narration(await result.get_final_response())

            context.result = ResponseStream(updates(), finalizer=finalize)