"""Customer-bound Responses continuation and SSE completion contracts."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import HTTPException

from bff.clients.continuation import completed_token, stream_with_continuation
from bff.config.settings import Settings
from bff.identity.conversation import _previous_response, _response_token


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None, responses_upstream_mode="local",
        responses_agent_endpoint="http://agent.test/responses",
        jwt_secret_key="synthetic-continuation-secret-for-tests",
    )


@pytest.mark.parametrize("change", ["user", "mode", "endpoint", "signature", "legacy", "empty", "long"])
def test_continuation_rejects_wrong_scope_or_invalid_token(settings: Settings, change: str) -> None:
    token = _response_token("resp_first", "customer-a", settings)
    user = "customer-a"
    if change == "user":
        user = "customer-b"
    elif change == "mode":
        settings = settings.model_copy(update={"responses_upstream_mode": "foundry"})
    elif change == "endpoint":
        settings = settings.model_copy(update={"responses_agent_endpoint": "http://other.test"})
    elif change == "signature":
        token = token[:-1] + ("0" if token[-1] != "0" else "1")
    elif change == "legacy":
        token = "v1.legacy.signature"
    elif change == "empty":
        token = ""
    else:
        token = "x" * 2049
    with pytest.raises(HTTPException) as error:
        _previous_response(token, user, settings)
    assert error.value.status_code == 403
    assert error.value.detail == {"code": "ACCESS_DENIED"}


@pytest.mark.parametrize("payload", [
    {}, {"id": "resp", "status": "failed"}, {"id": "", "status": "completed"},
    {"id": 7, "status": "completed"}, {"id": "r" * 513, "status": "completed"}, [],
])
def test_json_requires_valid_completed_response(settings: Settings, payload: object) -> None:
    assert completed_token(json.dumps(payload).encode(), "customer-a", settings) is None


class EventStream(httpx.AsyncByteStream):
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for offset in range(0, len(self.body), 13):
            yield self.body[offset:offset + 13]

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.parametrize("ending", ["\n\n", ""])
async def test_stream_parses_multiline_and_eof_and_closes(settings: Settings, ending: str) -> None:
    body = ('event: response.completed\r\n'
            'data: {"type":"response.completed",\r\n'
            'data: "response":{"id":"resp_first","status":"completed"}}' + ending)
    stream = EventStream(body.encode())
    response = httpx.Response(200, stream=stream)
    output = b"".join([chunk async for chunk in stream_with_continuation(
        response, "customer-a", settings
    )]).decode()
    controls = [json.loads(line[6:]) for line in output.splitlines()
                if line.startswith('data: {"type": "bff.continuation"')]
    assert len(controls) == 1
    assert _previous_response(controls[0]["token"], "customer-a", settings) == "resp_first"
    assert "CONTINUATION_UNAVAILABLE" not in output
    assert stream.closed


@pytest.mark.parametrize("suffix", [
    'data: {"type":"error"}\n\n',
    'data: {"type":"response.failed"}\n\n',
    'data: {"type":"response.incomplete"}\n\n',
    'data: invalid\n\n',
])
async def test_later_failure_never_publishes_checkpoint(settings: Settings, suffix: str) -> None:
    body = ('data: {"type":"response.completed",'
            '"response":{"id":"resp_first","status":"completed"}}\n\n' + suffix)
    stream = EventStream(body.encode())
    output = b"".join([chunk async for chunk in stream_with_continuation(
        httpx.Response(200, stream=stream), "customer-a", settings
    )]).decode()
    assert "bff.continuation" not in output
    assert output.count("CONTINUATION_UNAVAILABLE") == 1
    assert stream.closed


@pytest.mark.parametrize("suffix, available", [
    ('data: {"type":"response.completed","response":{"id":"resp_first","status":"completed"}}\n\n', True),
    ('data: {"type":"response.completed","response":{"id":"resp_other","status":"completed"}}\n\n', False),
    ('data: ' + 'x' * 1_048_577 + '\n\n', False),
], ids=["same-checkpoint", "conflicting-checkpoint", "oversized-event"])
async def test_duplicate_and_oversized_events(
    settings: Settings, suffix: str, available: bool
) -> None:
    body = ('data: {"type":"response.completed",'
            '"response":{"id":"resp_first","status":"completed"}}\n\n' + suffix)
    stream = EventStream(body.encode())
    output = b"".join([chunk async for chunk in stream_with_continuation(
        httpx.Response(200, stream=stream), "customer-a", settings
    )]).decode()
    assert ("bff.continuation" in output) is available
    assert ("CONTINUATION_UNAVAILABLE" in output) is not available
    assert stream.closed


@pytest.mark.parametrize("body", [b"", b'data: {"type":"response.completed"}\n\n'])
async def test_missing_checkpoint_fails_closed(settings: Settings, body: bytes) -> None:
    stream = EventStream(body)
    output = b"".join([chunk async for chunk in stream_with_continuation(
        httpx.Response(200, stream=stream), "customer-a", settings
    )]).decode()
    assert "bff.continuation" not in output
    assert output.count("CONTINUATION_UNAVAILABLE") == 1
    assert stream.closed
