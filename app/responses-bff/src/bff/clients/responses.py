"""Responses transport ownership; never retry effectful requests."""

from collections.abc import AsyncIterator
import httpx
from fastapi import HTTPException

async def _stream_response(response: httpx.Response) -> AsyncIterator[bytes]:
    try:
        async for chunk in response.aiter_raw():
            yield chunk
    finally:
        await response.aclose()


async def send_response(client: httpx.AsyncClient, request: httpx.Request) -> httpx.Response:
    try:
        return await client.send(request, stream=True)
    except httpx.RequestError as error:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE"}) from error


async def read_response(response: httpx.Response) -> bytes:
    try:
        return await response.aread()
    except httpx.RequestError as error:
        raise HTTPException(status_code=503, detail={"code": "SERVICE_UNAVAILABLE"}) from error
    finally:
        await response.aclose()
