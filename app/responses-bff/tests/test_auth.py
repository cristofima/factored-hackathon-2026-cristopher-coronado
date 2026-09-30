"""Tests for stateless application JWT issuance and validation."""

from __future__ import annotations

from datetime import date, datetime, timezone

import jwt
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from pwdlib import PasswordHash

from bff.main import create_app
from bff.settings import Settings
from banking_shared.models import Product, User

TEST_SECRET = "test-secret-key-with-at-least-32-bytes"
TEST_PASSWORD = "correct-horse-battery-staple"
TEST_USER = User(
    id="user-1",
    customer_id="customer-1",
    email="demo@example.com",
    password_hash=PasswordHash.recommended().hash(TEST_PASSWORD),
    locale="es",
)


class StubUserRepository:
    def __init__(self, user: User | None = TEST_USER, error: Exception | None = None) -> None:
        self.user = user
        self.error = error
        self.requested_email: str | None = None

    def find_by_email(self, email: str) -> User | None:
        self.requested_email = email
        if self.error:
            raise self.error
        return self.user


    def find_customer_name(self, user_id: str, customer_id: str) -> str | None:
        if self.error:
            raise self.error
        if self.user and self.user.id == user_id and self.user.customer_id == customer_id:
            return "Mariana Flores"
        return None

    def list_accounts(self, user_id: str, customer_id: str) -> list[Product]:
        if self.error:
            raise self.error
        if not self.user or self.user.id != user_id or self.user.customer_id != customer_id:
            return []
        return [Product(
            product_id="account-1", customer_id=customer_id,
            product_type="Cuenta Ahorro", currency="USD", product_status="Activa",
            opening_date=date(2026, 1, 15), product_number="12345678",
        )]


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        responses_upstream_mode="local",
        jwt_secret_key=TEST_SECRET,
        jwt_access_token_minutes=5,
    )


async def test_login_issues_valid_short_lived_jwt() -> None:
    settings = _settings()
    repository = StubUserRepository()
    app = create_app(settings, user_repository=repository)
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
    assert body["user"]["name"] == "Mariana Flores"
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
    assert repository.requested_email == "demo@example.com"


async def test_login_rejects_invalid_credentials_without_token() -> None:
    app = create_app(_settings(), user_repository=StubUserRepository())
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/auth/login",
                json={"email": "demo@example.com", "password": "wrong"},
            )

    assert response.status_code == 401
    assert "access_token" not in response.text


async def test_me_restores_identity_from_bearer_token() -> None:
    app = create_app(_settings(), user_repository=StubUserRepository())
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
        "name": "Mariana Flores",
    }


async def test_login_is_unavailable_without_jwt_configuration() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            responses_upstream_mode="local",
        ),
        user_repository=StubUserRepository(),
    )
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/auth/login",
                json={"email": "demo@example.com", "password": TEST_PASSWORD},
            )

    assert response.status_code == 503


async def test_login_rejects_unknown_user_without_token() -> None:
    app = create_app(_settings(), user_repository=StubUserRepository(user=None))
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/auth/login",
                json={"email": "missing@example.com", "password": TEST_PASSWORD},
            )

    assert response.status_code == 401
    assert "access_token" not in response.text


async def test_login_is_unavailable_when_database_lookup_fails() -> None:
    app = create_app(
        _settings(),
        user_repository=StubUserRepository(error=RuntimeError("DATABASE_URL is required")),
    )
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/auth/login",
                json={"email": "demo@example.com", "password": TEST_PASSWORD},
            )

    assert response.status_code == 503
    assert response.json()["detail"] == "Authentication is temporarily unavailable"


async def test_me_is_unavailable_when_profile_lookup_fails() -> None:
    repository = StubUserRepository()
    app = create_app(_settings(), user_repository=repository)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            login_response = await client.post(
                "/auth/login",
                json={"email": "demo@example.com", "password": TEST_PASSWORD},
            )
            repository.error = RuntimeError("Database is unavailable")
            response = await client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
            )

    assert response.status_code == 503
    assert response.json()["detail"] == "User profile is temporarily unavailable"


async def test_accounts_returns_persisted_fields_for_verified_identity() -> None:
    repository = StubUserRepository()
    app = create_app(_settings(), user_repository=repository)
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            login_response = await client.post(
                "/auth/login", json={"email": "demo@example.com", "password": TEST_PASSWORD},
            )
            headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}
            response = await client.get("/auth/me/accounts?customer_id=foreign", headers=headers)
            repository.error = RuntimeError("Database unavailable")
            unavailable = await client.get("/auth/me/accounts", headers=headers)

    assert response.status_code == 200
    assert response.json() == [{
        "id": "account-1", "type": "Cuenta Ahorro", "status": "Activa",
        "opened": "2026-01-15", "number": "12345678", "currency": "USD",
    }]
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == "Accounts are temporarily unavailable"


async def test_accounts_requires_bearer_identity() -> None:
    app = create_app(_settings(), user_repository=StubUserRepository())
    async with LifespanManager(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/auth/me/accounts")

    assert response.status_code == 401