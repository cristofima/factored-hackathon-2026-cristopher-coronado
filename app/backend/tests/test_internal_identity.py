"""Tests for request-scoped internal identity delegation."""

from __future__ import annotations

import base64
import asyncio
from contextvars import ContextVar
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.common.internal_identity import create_mcp_authorization


SECRET = "test-secret-key-with-at-least-32-bytes"


def _identity(sub: str = "user-a", customer_id: str = "customer-a") -> str:
    payload = json.dumps(
        {"customer_id": customer_id, "sub": sub},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode()
    signature = hmac.new(SECRET.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"v1.{encoded}.{signature}"


def _bearer_payload(authorization: str) -> dict[str, object]:
    _, token = authorization.split(" ")
    _, encoded, _ = token.split(".")
    padding = "=" * (-len(encoded) % 4)
    return json.loads(base64.urlsafe_b64decode(encoded + padding))


def test_create_mcp_authorization_uses_current_request_identity() -> None:
    with patch("app.common.internal_identity.get_request_context") as get_context:
        get_context.return_value.user_id = _identity()

        authorization = create_mcp_authorization(SECRET)

    assert authorization.startswith("Bearer v1.")
    assert _identity() not in authorization
    assert _bearer_payload(authorization) == {
        "customer_id": "customer-a",
        "exp": pytest.approx(int(time.time()) + 60, abs=1),
        "sub": "user-a",
    }


def test_create_mcp_authorization_rejects_tampered_identity() -> None:
    with patch("app.common.internal_identity.get_request_context") as get_context:
        get_context.return_value.user_id = f"{_identity()}tampered"

        with pytest.raises(ValueError, match="signature"):
            create_mcp_authorization(SECRET)


async def test_concurrent_requests_do_not_leak_identity() -> None:
    current_identity: ContextVar[str | None] = ContextVar(
        "current_test_identity",
        default=None,
    )

    async def create_for(identity: str) -> dict[str, object]:
        token = current_identity.set(identity)
        try:
            await asyncio.sleep(0)
            return _bearer_payload(create_mcp_authorization(SECRET))
        finally:
            current_identity.reset(token)

    with patch(
        "app.common.internal_identity.get_request_context",
        side_effect=lambda: SimpleNamespace(user_id=current_identity.get()),
    ):
        first, second = await asyncio.gather(
            create_for(_identity("user-a", "customer-a")),
            create_for(_identity("user-b", "customer-b")),
        )

    assert (first["sub"], first["customer_id"]) == ("user-a", "customer-a")
    assert (second["sub"], second["customer_id"]) == ("user-b", "customer-b")