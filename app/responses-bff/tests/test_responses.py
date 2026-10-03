"""Tests for local and Foundry Responses upstream modes."""

from __future__ import annotations

import base64
import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
import re
from types import SimpleNamespace

import httpx
import httpcore
import jwt
import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from bff.auth import AuthenticatedUser
from bff.internal_identity import create_internal_identity
from bff.main import create_app
from bff.settings import Settings


TEST_SECRET = "test-secret-key-with-at-least-32-bytes"


@pytest.mark.parametrize("locale", ["es", "pt", "en", "en-US", "fr"])
def test_internal_identity_signs_verified_email_without_browser_credentials(locale: str) -> None:
    user = _authenticated_user("user-a")
    user = AuthenticatedUser(sub=user.sub, customer_id=user.customer_id,
                             email=user.email, locale=locale)

    identity = create_internal_identity(user, TEST_SECRET)

    version, encoded, signature = identity.split(".")
    payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    assert version == "v1"
    assert payload == {
        "sub": user.sub,
        "customer_id": user.customer_id,
        "email": user.email,
        "locale": user.locale,
    }
    assert hmac.compare_digest(
        signature,
        hmac.new(TEST_SECRET.encode(), encoded.encode(), hashlib.sha256).hexdigest(),
    )


class FakeCredential:
    def __init__(self) -> None:
        self.scopes: list[str] = []
        self.closed = False

    async def get_token(self, *scopes: str) -> SimpleNamespace:
        self.scopes.extend(scopes)
        return SimpleNamespace(token="foundry-access-token")

    async def close(self) -> None:
        self.closed = True


class SseStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b"event: response.completed\ndata: {}\n\n"


def _settings(mode: str) -> Settings:
    return Settings(
        responses_upstream_mode=mode,
        responses_agent_endpoint="http://agent.test/responses",
        jwt_secret_key=TEST_SECRET,
        internal_identity_secret=TEST_SECRET,
    )


def _token(user_id: str, settings: Settings) -> str:
    return jwt.encode(
        {
            "sub": user_id,
            "customer_id": f"customer-{user_id}",
            "email": f"{user_id}@example.com",
            "locale": "en-US",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        TEST_SECRET,
        algorithm="HS256",
    )


async def _post(app, token: str, payload: dict[str, object]) -> httpx.Response:
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/responses",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )


async def test_local_mode_uses_signed_internal_identity_without_azure_credential() -> None:
    settings = _settings("local")
    credential_factory_called = False

    def fail_if_called(_: Settings) -> FakeCredential:
        nonlocal credential_factory_called
        credential_factory_called = True
        raise AssertionError("Local mode must not create an Azure credential")

    async def upstream(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("http://agent.test/responses")
        assert "Authorization" not in request.headers
        assert "x-ms-user-identity" not in request.headers
        assert request.headers["x-agent-user-id"] == create_internal_identity(
            user=_authenticated_user("user-a"),
            secret=TEST_SECRET,
        )
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=SseStream(),
        )

    app = create_app(
        settings,
        transport=httpx.MockTransport(upstream),
        credential_factory=fail_if_called,
    )
    response = await _post(app, _token("user-a", settings), {"input": "Accounts", "stream": True})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,128}", response.headers["x-conversation-id"])
    assert response.text == "event: response.completed\ndata: {}\n\n"
    assert credential_factory_called is False


async def test_foundry_mode_uses_managed_credential_and_delegated_identity() -> None:
    settings = _settings("foundry")
    credential = FakeCredential()

    async def upstream(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer foundry-access-token"
        assert request.headers["x-ms-user-identity"] == create_internal_identity(
            user=_authenticated_user("user-a"),
            secret=TEST_SECRET,
        )
        assert "user_isolation_key" not in request.headers
        assert "chat_isolation_key" not in request.headers
        return httpx.Response(200, json={"status": "completed"})

    app = create_app(
        settings,
        transport=httpx.MockTransport(upstream),
        credential_factory=lambda _: credential,
    )
    response = await _post(app, _token("user-a", settings), {"input": "Accounts"})

    assert response.status_code == 200
    assert credential.scopes == ["https://ai.azure.com/.default"]
    assert credential.closed is True


def _authenticated_user(user_id: str) -> AuthenticatedUser:
    return AuthenticatedUser(
        sub=user_id,
        customer_id=f"customer-{user_id}",
        email=f"{user_id}@example.com",
        locale="en-US",
    )


async def test_conversation_cannot_cross_users() -> None:
    settings = _settings("local")

    async def upstream(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "completed"})

    app = create_app(settings, transport=httpx.MockTransport(upstream))
    first = await _post(app, _token("user-a", settings), {"input": "First turn"})
    second = await _post(
        app,
        _token("user-b", settings),
        {"input": "Second turn", "conversation": first.headers["x-conversation-id"]},
    )

    assert first.status_code == 200
    assert second.status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {"input": "Continue", "previous_response_id": "caresp_foreign"},
        {"input": "Continue", "conversation": 123},
    ],
)
async def test_invalid_continuation_is_rejected(payload: dict[str, object]) -> None:
    settings = _settings("local")
    app = create_app(settings)

    response = await _post(app, _token("user-a", settings), payload)

    assert response.status_code == 400


@pytest.mark.parametrize("incoming", [None, "valid", "invalid"])
@pytest.mark.parametrize("stream", [False, True])
async def test_w3c_context_propagates_to_agent(
    monkeypatch: pytest.MonkeyPatch, incoming: str | None, stream: bool
) -> None:
    captured: list[httpx.Headers] = []

    async def upstream(
        pool: httpcore.AsyncConnectionPool, request: httpcore.Request
    ) -> httpcore.Response:
        captured.append(httpx.Headers(request.headers))
        content = (
            b"event: response.completed\ndata: {}\n\n"
            if stream else b'{"status":"completed"}'
        )
        return httpcore.Response(200, content=content)

    monkeypatch.setattr(httpcore.AsyncConnectionPool, "handle_async_request", upstream)
    settings = _settings("local")
    app = create_app(settings)
    headers = {"Authorization": f"Bearer {_token('user-a', settings)}"}
    trace_id = "1234567890abcdef1234567890abcdef"
    parent_id = "1234567890abcdef"
    if incoming == "valid":
        headers.update(traceparent=f"00-{trace_id}-{parent_id}-01", tracestate="bank=opaque")
    elif incoming == "invalid":
        headers.update(traceparent="invalid", tracestate="bank=opaque")

    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/responses", json={"input": "Accounts", "stream": stream}, headers=headers
            )

    assert response.status_code == 200
    assert len(captured) == 1
    outbound = captured[0]["traceparent"]
    assert re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", outbound)
    assert outbound.split("-")[1] != "0" * 32
    assert outbound.split("-")[2] != parent_id
    if incoming == "valid":
        assert outbound.split("-")[1] == trace_id
        assert captured[0]["tracestate"] == "bank=opaque"
    else:
        assert outbound.split("-")[1] != trace_id
        assert "tracestate" not in captured[0]


async def test_concurrent_bff_requests_have_independent_traces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []
    both_requests = asyncio.Event()

    async def upstream(
        pool: httpcore.AsyncConnectionPool, request: httpcore.Request
    ) -> httpcore.Response:
        captured.append(httpx.Headers(request.headers)["traceparent"])
        if len(captured) == 2:
            both_requests.set()
        await asyncio.wait_for(both_requests.wait(), timeout=5)
        return httpcore.Response(200, content=b'{"status":"completed"}')

    monkeypatch.setattr(httpcore.AsyncConnectionPool, "handle_async_request", upstream)
    settings = _settings("local")
    app = create_app(settings)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            responses = await asyncio.gather(*(
                client.post(
                    "/responses", json={"input": "Accounts"},
                    headers={"Authorization": f"Bearer {_token(user, settings)}"},
                )
                for user in ("user-a", "user-b")
            ))

    assert [response.status_code for response in responses] == [200, 200]
    assert len({value.split("-")[1] for value in captured}) == 2