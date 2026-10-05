"""Publish customer-bound continuation only after an upstream response completes."""

import json
from collections.abc import AsyncIterator

import httpx

from bff.config.settings import Settings
from bff.identity.conversation import _response_token


def completed_token(content: bytes, user_id: str, settings: Settings) -> str | None:
    try:
        response = json.loads(content)
    except (ValueError, UnicodeError):
        return None
    if not isinstance(response, dict) or response.get("status") != "completed":
        return None
    response_id = response.get("id")
    if not isinstance(response_id, str) or not response_id or len(response_id) > 512:
        return None
    return _response_token(response_id, user_id, settings)


async def stream_with_continuation(
    response: httpx.Response, user_id: str, settings: Settings
) -> AsyncIterator[bytes]:
    data: list[str] = []
    size = 0
    last_line = ""
    token: str | None = None
    failed = False

    def observe_completion() -> None:
        nonlocal token, failed
        if size > 1_048_576:
            failed = True
            return
        if not data:
            return
        try:
            event = json.loads("\n".join(data))
        except ValueError:
            if "\n".join(data) != "[DONE]":
                failed = True
            return
        if not isinstance(event, dict):
            failed = True
            return
        if event.get("type") in {"error", "response.failed", "response.incomplete"}:
            failed = True
        if event.get("type") == "response.completed":
            candidate = completed_token(
                json.dumps(event.get("response")).encode(), user_id, settings
            )
            if not candidate or (token is not None and token != candidate):
                failed = True
            token = candidate

    try:
        async for line in response.aiter_lines():
            last_line = line
            if line.startswith("data:"):
                value = line[5:].removeprefix(" ")
                size += len(value)
                if size <= 1_048_576:
                    data.append(value)
            yield f"{line}\n".encode()
            if not line:
                observe_completion()
                data.clear()
                size = 0
        if last_line:
            yield b"\n"
            observe_completion()
        if response.is_success:
            if token and not failed:
                control = json.dumps({"type": "bff.continuation", "token": token})
                yield f"data: {control}\n\n".encode()
            else:
                yield b'data: {"type":"error","code":"CONTINUATION_UNAVAILABLE","allow_retry":false}\n\n'
    finally:
        await response.aclose()
