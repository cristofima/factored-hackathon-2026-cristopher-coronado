"""Authenticated proxy for a local or Foundry Responses agent."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import AsyncIterator
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse

from bff.identity.models import AuthenticatedUser
from bff.identity.authentication import get_customer_user
from bff.identity.conversation import _conversation_token, _validate_conversation
from bff.identity.responses import AsyncCredential, _upstream_headers
from bff.clients.responses import _stream_response, read_response, send_response
from bff.config.settings import Settings


router = APIRouter(prefix="/responses")


@router.post("")
async def create_response(
    payload: dict[str, Any],
    request: Request,
    user: Annotated[AuthenticatedUser, Depends(get_customer_user)],
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
    upstream = await send_response(client, upstream_request)

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