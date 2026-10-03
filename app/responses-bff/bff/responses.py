"""Authenticated proxy for a local or Foundry Responses agent."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import AsyncIterator
from typing import Annotated, Any, Protocol

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse

from bff.auth import AuthenticatedUser, get_authenticated_user
from bff.internal_identity import create_internal_identity
from bff.settings import Settings


class AsyncCredential(Protocol):
    """Credential operations used by the BFF."""

    async def get_token(self, *scopes: str) -> Any: ...

    async def close(self) -> None: ...


router = APIRouter(prefix="/responses")


def _conversation_token(user_id: str, settings: Settings) -> str:
    conversation_id = secrets.token_urlsafe(24)
    signature = _conversation_signature(user_id, conversation_id, settings)
    return f"{conversation_id}_{signature}"


def _validate_conversation(token: str, user_id: str, settings: Settings) -> None:
    try:
        conversation_id, signature = token.rsplit("_", maxsplit=1)
    except ValueError:
        raise _forbidden_conversation() from None

    expected = _conversation_signature(user_id, conversation_id, settings)
    if not hmac.compare_digest(signature, expected):
        raise _forbidden_conversation()


def _conversation_signature(user_id: str, conversation_id: str, settings: Settings) -> str:
    if not settings.jwt_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE"},
        )
    return hmac.new(
        settings.jwt_secret_key.encode(),
        f"{user_id}:{conversation_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _forbidden_conversation() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "ACCESS_DENIED"},
    )


async def _upstream_headers(
    request: Request,
    user: AuthenticatedUser,
    stream: bool,
) -> dict[str, str]:
    settings: Settings = request.app.state.settings
    headers = {"Accept": "text/event-stream" if stream else "application/json"}
    if not settings.internal_identity_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "SERVICE_UNAVAILABLE"},
        )
    internal_identity = create_internal_identity(user, settings.internal_identity_secret)
    if settings.responses_upstream_mode == "foundry":
        credential: AsyncCredential = request.app.state.azure_credential
        token = await credential.get_token(settings.responses_token_scope)
        headers["Authorization"] = f"Bearer {token.token}"
        headers["x-ms-user-identity"] = internal_identity
    else:
        headers["x-agent-user-id"] = internal_identity
    return headers


async def _stream_response(response: httpx.Response) -> AsyncIterator[bytes]:
    try:
        async for chunk in response.aiter_raw():
            yield chunk
    finally:
        await response.aclose()


@router.post("")
async def create_response(
    payload: dict[str, Any],
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_authenticated_user)],
) -> Response:
    """Forward a Responses request to the configured trusted upstream."""
    if payload.get("previous_response_id"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_REQUEST"},
        )

    requested_conversation = payload.get("conversation")
    if requested_conversation is not None and not isinstance(requested_conversation, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_REQUEST"},
        )

    settings: Settings = request.app.state.settings
    conversation = requested_conversation or _conversation_token(user.sub, settings)
    _validate_conversation(conversation, user.sub, settings)

    # The hosted Foundry Responses gateway validates "conversation" against its own
    # platform-managed Conversation object ids (e.g. "conv_..."); our opaque, BFF-signed
    # token can never match that format and upstream rejects it as a malformed identifier.
    # Only the local agent host (which treats "conversation" as an arbitrary state-store
    # key) can accept it, so omit the field entirely in foundry mode.
    upstream_payload = dict(payload)
    if settings.responses_upstream_mode == "local":
        upstream_payload["conversation"] = conversation
    else:
        upstream_payload.pop("conversation", None)

    client: httpx.AsyncClient = request.app.state.http_client
    upstream_request = client.build_request(
        "POST",
        settings.responses_agent_endpoint,
        json=upstream_payload,
        headers=await _upstream_headers(request, user, bool(payload.get("stream"))),
    )
    upstream = await client.send(upstream_request, stream=True)

    response_headers = {"X-Conversation-Id": conversation}
    content_type = upstream.headers.get("content-type", "application/json")
    if content_type.startswith("text/event-stream"):
        return StreamingResponse(
            _stream_response(upstream),
            status_code=upstream.status_code,
            media_type="text/event-stream",
            headers=response_headers,
        )

    content = await upstream.aread()
    await upstream.aclose()
    return Response(
        content=content,
        status_code=upstream.status_code,
        media_type=content_type,
        headers=response_headers,
    )