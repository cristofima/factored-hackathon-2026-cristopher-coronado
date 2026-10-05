"""Transport failures retain controlled errors and never retry writes."""

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from bff.clients.responses import _stream_response, read_response, send_response


async def test_failed_effectful_send_is_not_retried() -> None:
    request = httpx.Request("POST", "http://synthetic.invalid/responses")
    client = AsyncMock(spec=httpx.AsyncClient)
    client.send.side_effect = httpx.ConnectError("synthetic failure", request=request)
    with pytest.raises(HTTPException) as caught:
        await send_response(client, request)
    assert caught.value.status_code == 503
    assert caught.value.detail == {"code": "SERVICE_UNAVAILABLE"}
    client.send.assert_awaited_once_with(request, stream=True)


@pytest.mark.parametrize("failure", [httpx.ReadError("synthetic failure"), asyncio.CancelledError()])
async def test_response_read_always_closes(failure: BaseException) -> None:
    response = AsyncMock(spec=httpx.Response)
    response.aread.side_effect = failure
    expected = HTTPException if isinstance(failure, httpx.ReadError) else asyncio.CancelledError
    with pytest.raises(expected):
        await read_response(response)
    response.aclose.assert_awaited_once()


async def test_stream_abandonment_closes_upstream() -> None:
    response = AsyncMock(spec=httpx.Response)

    async def chunks() -> AsyncIterator[bytes]:
        yield b"unchanged raw SSE chunk"
        yield b"second chunk"

    response.aiter_raw = chunks
    stream = _stream_response(response)
    assert await anext(stream) == b"unchanged raw SSE chunk"
    await stream.aclose()
    response.aclose.assert_awaited_once()
