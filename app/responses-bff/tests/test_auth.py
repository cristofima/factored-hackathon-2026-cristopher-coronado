"""Tests for stateless application JWT issuance and validation."""

from __future__ import annotations

from datetime import datetime, timezone

import jwt
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from pwdlib import PasswordHash

from bff.main import create_app
from bff.settings import ConfiguredUser, Settings

TEST_SECRET = "test-secret-key-with-at-least-32-bytes"
TEST_PASSWORD = "correct-horse-battery-staple"


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        responses_upstream_mode="local",
        jwt_secret_key=TEST_SECRET,
        jwt_access_token_minutes=5,
        auth_users=[
            ConfiguredUser(
                id="user-1",
                customer_id="customer-1",
                email="demo@example.com",
                password_hash=PasswordHash.recommended().hash(TEST_PASSWORD),
                locale="es",
            )
        ],
    )


async def test_login_issues_valid_short_lived_jwt() -> None:
    settings = _settings()
    app = create_app(settings)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/auth/login",
                json={"email": "DEMO@example.com", "password": TEST_PASSWORD},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 300
    claims = jwt.decode(
        body["access_token"],
        TEST_SECRET,
        algorithms=["HS256"],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )
    assert claims["sub"] == "user-1"
    assert claims["customer_id"] == "customer-1"
    assert claims["locale"] == "es"
    assert claims["exp"] > datetime.now(timezone.utc).timestamp()


async def test_login_rejects_invalid_credentials_without_token() -> None:
    app = create_app(_settings())
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/auth/login",
                json={"email": "demo@example.com", "password": "wrong"},
            )

    assert response.status_code == 401
    assert "access_token" not in response.text


async def test_me_restores_identity_from_bearer_token() -> None:
    app = create_app(_settings())
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            login_response = await client.post(
                "/auth/login",
                json={"email": "demo@example.com", "password": TEST_PASSWORD},
            )
            response = await client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
            )

    assert response.status_code == 200
    assert response.json() == {
        "sub": "user-1",
        "customer_id": "customer-1",
        "email": "demo@example.com",
        "locale": "es",
    }


async def test_login_is_unavailable_without_configured_users() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            responses_upstream_mode="local",
            jwt_secret_key=TEST_SECRET,
        )
    )
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/auth/login",
                json={"email": "demo@example.com", "password": TEST_PASSWORD},
            )

    assert response.status_code == 503