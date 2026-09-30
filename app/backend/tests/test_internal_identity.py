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
from unittest.mock import MagicMock, patch

import pytest

from app.common.internal_identity import create_mcp_authorization
from app.helpers.user_profile_helper import UserProfileHelper
from app.helpers.user_profile_provider import UserProfileProvider


SECRET = "test-secret-key-with-at-least-32-bytes"


def _identity(
    sub: str = "user-a", customer_id: str = "customer-a", email: str | None = None
) -> str:
    claims = {"customer_id": customer_id, "sub": sub}
    if email is not None:
        claims["email"] = email
    payload = json.dumps(
        claims,
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


async def test_profile_provider_injects_verified_request_email() -> None:
    context = MagicMock()
    provider = UserProfileProvider(SECRET)
    with patch("app.common.internal_identity.get_request_context") as get_context:
        get_context.return_value.user_id = _identity(email="real-user@example.com")

        await provider.before_run(agent=None, session=None, context=context, state={})
        authorization = create_mcp_authorization(SECRET)

    context.extend_instructions.assert_any_call(
        provider.source_id, "Email: real-user@example.com"
    )
    assert "bob.user@contoso.com" not in str(context.extend_instructions.call_args_list)
    assert "email" not in _bearer_payload(authorization)


@pytest.mark.parametrize(
    ("identity", "error_type", "message"),
    [
        (None, RuntimeError, "Authenticated request identity is required"),
        (_identity(), ValueError, "Authenticated request email is required"),
        (_identity(email="   "), ValueError, "Invalid internal identity email"),
        (
            _identity(email="real-user@example.com") + "tampered",
            ValueError,
            "Invalid internal identity signature",
        ),
    ],
)
async def test_profile_provider_rejects_unverified_or_missing_email(
    identity: str | None, error_type: type[Exception], message: str
) -> None:
    context = MagicMock()
    with patch("app.common.internal_identity.get_request_context") as get_context:
        get_context.return_value.user_id = identity

        with pytest.raises(error_type, match=message):
            await UserProfileProvider(SECRET).before_run(
                agent=None, session=None, context=context, state={}
            )

    context.extend_instructions.assert_not_called()


async def test_concurrent_profiles_use_each_requests_verified_email() -> None:
    current_identity: ContextVar[str | None] = ContextVar("profile_identity", default=None)
    provider = UserProfileProvider(SECRET)

    async def profile_for(email: str) -> MagicMock:
        token = current_identity.set(_identity(sub=email, customer_id=email, email=email))
        context = MagicMock()
        try:
            await asyncio.sleep(0)
            await provider.before_run(agent=None, session=None, context=context, state={})
            assert UserProfileHelper.get_user_id(SECRET) == email
            return context
        finally:
            current_identity.reset(token)

    with patch(
        "app.common.internal_identity.get_request_context",
        side_effect=lambda: SimpleNamespace(user_id=current_identity.get()),
    ):
        first, second = await asyncio.gather(
            profile_for("user-a@example.com"), profile_for("user-b@example.com")
        )

    first.extend_instructions.assert_any_call(provider.source_id, "Email: user-a@example.com")
    second.extend_instructions.assert_any_call(provider.source_id, "Email: user-b@example.com")