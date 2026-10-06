"""Provider refusal normalization and ordinary output preservation."""

from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import (
    Agent, AgentContext, AgentResponse, AgentResponseUpdate, ChatResponse,
    ChatResponseUpdate, Content, Message, ResponseStream,
)
from agent_framework_foundry import FoundryChatClient
from openai.types.responses import ResponseRefusalDeltaEvent

from app.adapters.refusal_locale_middleware import RefusalLocaleMiddleware
from app.common.internal_identity import InternalPrincipal


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("locale, expected", [
    ("en", "I cannot assist with that request."),
    ("es", "No puedo ayudar con esa solicitud."),
    ("pt", "Não posso ajudar com essa solicitação."),
])
async def test_refusal_uses_profile_locale_and_preserves_metadata(
    stream: bool, locale: str, expected: str,
) -> None:
    context = AgentContext(agent=MagicMock(), messages=[], stream=stream)
    chunks = ["I'm sorry, ", "but I cannot assist with that request."]
    contents = [Content.from_text(
        chunk, additional_properties={"model_output_kind": "refusal", "source": "provider"},
    ) for chunk in chunks]
    response = AgentResponse(messages=[Message(role="assistant", contents=contents)])

    async def updates() -> AsyncIterator[AgentResponseUpdate]:
        for content in contents:
            yield AgentResponseUpdate(contents=[content], role="assistant", message_id="r1")

    async def run() -> None:
        context.result = ResponseStream(updates(), finalizer=lambda _: response) if stream else response

    with patch("app.adapters.refusal_locale_middleware.get_internal_principal", return_value=
               InternalPrincipal(sub="test-user", customer_id="test-customer", locale=locale)):
        await RefusalLocaleMiddleware("synthetic-secret").process(context, run)
    if stream:
        emitted = [update async for update in context.result]
        assert "".join(content.text for update in emitted for content in update.contents) == expected
        result = await context.result.get_final_response()
    else:
        result = context.result
    assert result.text == expected
    assert [content.text for content in contents] == chunks
    assert all(content.additional_properties == {
        "model_output_kind": "refusal", "source": "provider",
    } for message in result.messages for content in message.contents)


@pytest.mark.parametrize("stream", [False, True])
async def test_unmarked_text_is_never_translated(stream: bool) -> None:
    text = "I'm sorry, but I cannot assist with that request. Balance: USD 10."
    response = AgentResponse(messages=[Message(role="assistant", contents=[Content.from_text(text)])])
    context = AgentContext(agent=MagicMock(), messages=[], stream=stream)

    async def updates() -> AsyncIterator[AgentResponseUpdate]:
        yield AgentResponseUpdate(contents=[Content.from_text(text)], role="assistant")

    async def run() -> None:
        context.result = ResponseStream(updates(), finalizer=lambda _: response) if stream else response

    with patch("app.adapters.refusal_locale_middleware.get_internal_principal", return_value=
               InternalPrincipal(sub="test-user", customer_id="test-customer", locale="es")):
        await RefusalLocaleMiddleware("synthetic-secret").process(context, run)
    result = await context.result.get_final_response() if stream else context.result
    assert result.text == text


@pytest.mark.parametrize("stream", [False, True])
async def test_foundry_sdk_refusal_event_is_localized(stream: bool) -> None:
    client = FoundryChatClient(
        project_endpoint="https://example.services.ai.azure.com/api/projects/test",
        model="test-model", credential=MagicMock(),
    )

    def model_response(*args: object, **kwargs: object) -> ResponseStream:
        async def updates() -> AsyncIterator[ChatResponseUpdate]:
            for index, text in enumerate(["I'm sorry, ", "but I cannot assist."]):
                event = ResponseRefusalDeltaEvent(
                    type="response.refusal.delta", delta=text, item_id="refusal-1",
                    output_index=0, content_index=0, sequence_number=index,
                )
                yield client._parse_chunk_from_openai(event, {}, {})

        return ResponseStream(updates(), finalizer=ChatResponse.from_updates)

    async def final_model_response(*args: object, **kwargs: object) -> ChatResponse:
        return await model_response().get_final_response()

    agent = Agent(client=client, middleware=[RefusalLocaleMiddleware("synthetic-secret")])
    provider = model_response if stream else final_model_response
    with patch.object(client, "_inner_get_response", provider), patch(
        "app.adapters.refusal_locale_middleware.get_internal_principal",
        return_value=InternalPrincipal(sub="test-user", customer_id="test-customer", locale="es"),
    ):
        if stream:
            result_stream = agent.run("synthetic request", stream=True)
            emitted = [update async for update in result_stream]
            assert "".join(update.text for update in emitted) == "No puedo ayudar con esa solicitud."
            result = await result_stream.get_final_response()
        else:
            result = await agent.run("synthetic request")
    assert result.text == "No puedo ayudar con esa solicitud."


async def test_missing_identity_fails_before_model_call() -> None:
    context = AgentContext(agent=MagicMock(), messages=[], stream=False)
    called = False

    async def run() -> None:
        nonlocal called
        called = True

    with patch("app.adapters.refusal_locale_middleware.get_internal_principal",
               side_effect=RuntimeError("Authenticated request identity is required")):
        with pytest.raises(RuntimeError, match="Authenticated request identity"):
            await RefusalLocaleMiddleware("synthetic-secret").process(context, run)
    assert called is False
