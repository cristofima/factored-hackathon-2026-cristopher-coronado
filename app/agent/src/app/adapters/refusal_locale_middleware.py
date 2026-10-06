"""Localize provider-marked refusals without translating ordinary model output."""

from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from copy import copy

from agent_framework import (
    AgentContext, AgentMiddleware, AgentResponse, AgentResponseUpdate, Content, ResponseStream,
)

from app.common.internal_identity import get_internal_principal


_REFUSALS = {
    "en": "I cannot assist with that request.",
    "es": "No puedo ayudar con esa solicitud.",
    "pt": "Não posso ajudar com essa solicitação.",
}


def _is_refusal(content: Content) -> bool:
    return (
        content.type == "text"
        and content.additional_properties.get("model_output_kind") == "refusal"
    )


def _localize_response(response: AgentResponse, text: str) -> AgentResponse:
    response = copy(response)
    response.messages = [copy(message) for message in response.messages]
    for message in response.messages:
        emitted = False
        contents: list[Content] = []
        for original in message.contents:
            content = copy(original)
            if _is_refusal(content):
                if emitted:
                    continue
                content.text = text
                emitted = True
            contents.append(content)
        message.contents = contents
    return response


class RefusalLocaleMiddleware(AgentMiddleware):
    def __init__(self, internal_identity_secret: str) -> None:
        self._identity_secret = internal_identity_secret

    async def process(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        locale = get_internal_principal(self._identity_secret).locale
        text = _REFUSALS.get(locale, _REFUSALS["en"])
        await call_next()
        result = context.result
        if isinstance(result, AgentResponse):
            context.result = _localize_response(result, text)
        elif isinstance(result, ResponseStream):
            async def updates() -> AsyncIterator[AgentResponseUpdate]:
                emitted: set[str | None] = set()
                async for update in result:
                    update = copy(update)
                    update.contents = [copy(content) for content in update.contents]
                    for content in update.contents:
                        if _is_refusal(content):
                            content.text = "" if update.message_id in emitted else text
                            emitted.add(update.message_id)
                    yield update

            async def finalize(
                _buffered: Sequence[AgentResponseUpdate],
            ) -> AgentResponse:
                return _localize_response(await result.get_final_response(), text)

            context.result = ResponseStream(updates(), finalizer=finalize)
