"""Auth HTTP facade, per-request revocation, and role authorization regressions."""
from collections.abc import Callable
from typing import Any

from datetime import datetime, timedelta, timezone
import json

import httpx
import jwt
import pytest
from asgi_lifespan import LifespanManager

from bff.main import create_app
from bff.settings import Settings

SECRET = "synthetic-signing-secret-at-least-32-bytes"


def settings() -> Settings:
    options: dict[str, Any] = {"_env_file": None}
    return Settings(**options, responses_upstream_mode="local", jwt_secret_key=SECRET,
                    auth_internal_secret="synthetic-internal-secret")


def profile(role: str = "customer") -> dict[str, Any]:
    result = {"sub": "user-1", "email": "demo@example.com", "locale": "es",
              "role": role, "identity_version": 1, "name": "Demo User"}
    if role == "customer":
        result["customer_id"] = "customer-1"
    return result


def token(user: dict[str, Any], **changes: Any) -> str:
    payload = {k: v for k, v in user.items() if k != "name"}
    payload.update(iss=settings().jwt_issuer, aud=settings().jwt_audience,
                   exp=datetime.now(timezone.utc) + timedelta(minutes=5))
    payload.update(changes)
    return jwt.encode(payload, SECRET, algorithm="HS256")


async def request(handler: Callable[[httpx.Request], httpx.Response], method: str, path: str, user: dict[str, Any] | None = None,
                  bearer: str | None = None, body: dict[str, Any] | None = None) -> httpx.Response:
    app = create_app(settings(), auth_transport=httpx.MockTransport(handler))
    async with LifespanManager(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://bff") as client:
            headers = {"Authorization": "Bearer " + (bearer or token(user))} if user else {}
            return await client.request(method, path, headers=headers, json=body)


@pytest.mark.parametrize("role", ["customer", "operator", "admin"])
async def test_login_and_me_roles(role: str) -> None:
    user = profile(role)
    bearer = token(user)
    calls = []
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if req.url.path == "/auth/login":
            assert json.loads(req.content) == {"email": "demo@example.com", "password": "synthetic-password"}
            return httpx.Response(200, json={"access_token": token(user), "token_type": "bearer",
                                            "expires_in": 300, "user": user})
        if req.url.path == "/internal/introspect":
            assert req.headers["Authorization"] == "Bearer synthetic-internal-secret"
            assert json.loads(req.content) == {"token": bearer}
            assert req.extensions["timeout"]["read"] == 3
        else:
            assert req.headers["Authorization"] == "Bearer " + bearer
        return httpx.Response(200, json=user)
    result = await request(handler, "POST", "/auth/login", body={"email": "demo@example.com", "password": "synthetic-password"})
    assert result.status_code == 200
    assert result.json()["user"] == user
    result = await request(handler, "GET", "/auth/me", user, bearer=bearer)
    assert result.status_code == 200
    assert result.json() == user
    assert calls == ["/auth/login", "/internal/introspect", "/auth/me"]


async def test_no_introspection_cache() -> None:
    user = profile()
    calls = []
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if req.url.path == "/internal/introspect" and calls.count(req.url.path) == 2:
            return httpx.Response(401)
        return httpx.Response(200, json=user)
    app = create_app(settings(), auth_transport=httpx.MockTransport(handler))
    async with LifespanManager(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://bff") as client:
            headers = {"Authorization": "Bearer " + token(user)}
            assert (await client.get("/auth/me", headers=headers)).status_code == 200
            revoked = await client.get("/auth/me", headers=headers)
            assert revoked.status_code == 401
            assert revoked.headers["www-authenticate"] == "Bearer"
    assert calls == ["/internal/introspect", "/auth/me", "/internal/introspect"]


@pytest.mark.parametrize("role", ["operator", "admin"])
async def test_staff_cannot_chat(role: str) -> None:
    user = profile(role)
    result = await request(lambda req: httpx.Response(200, json=user), "POST", "/responses", user,
                           body={"input": "hello"})
    assert result.status_code == 403


@pytest.mark.parametrize("role", ["customer", "operator"])
@pytest.mark.parametrize("method,path", [("GET", "/admin/operators"),
    ("GET", "/admin/customers"), ("POST", "/admin/customers/customer/activate"),
    ("POST", "/admin/customers/customer/deactivate")])
async def test_nonadmin_denied(role: str, method: str, path: str) -> None:
    user = profile(role)
    calls = []
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        return httpx.Response(200, json=user)
    result = await request(handler, method, path, user)
    assert result.status_code == 403
    assert calls == ["/internal/introspect"]


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/admin/operators", None),
    ("GET", "/admin/customers", None),
    ("POST", "/admin/customers/user-2/activate", None),
    ("POST", "/admin/customers/user-2/deactivate", None),
    ("POST", "/admin/operators", {"email": "staff@example.com", "password": "synthetic-password", "locale": "pt", "first_name": "Staff", "last_name": "User"}),
    ("POST", "/admin/operators/user-2/activate", None),
    ("POST", "/admin/operators/user-2/deactivate", None),
    ("POST", "/admin/operators/user-2/reset-password", {"password": "synthetic-new-password"}),
])
async def test_admin_allowlist(method: str, path: str, body: dict[str, Any] | None) -> None:
    user = profile("admin")
    bearer = token(user)
    calls = []
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if req.url.path == "/internal/introspect":
            return httpx.Response(200, json=user)
        assert req.url.path == path
        assert req.method == method
        assert req.headers["Authorization"] == "Bearer " + bearer
        assert json.loads(req.content) == body if body is not None else not req.content
        return httpx.Response(200, json={"ok": True})
    result = await request(handler, method, path, user, bearer=bearer, body=body)
    assert result.status_code == 200
    assert result.json() == {"ok": True}
    assert calls == ["/internal/introspect", path]


@pytest.mark.parametrize("field,value", [
    ("first_name", None), ("last_name", None), ("first_name", " "), ("last_name", " "),
    ("first_name", "x" * 51), ("last_name", "x" * 51),
    ("email", "a" * 60 + "@" + "b" * 56 + ".com"), ("name", "Legacy name"),
])
async def test_operator_invalid_fields_never_forwarded(field: str, value: Any) -> None:
    user = profile("admin")
    calls: list[str] = []
    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        assert req.url.path == "/internal/introspect"
        return httpx.Response(200, json=user)
    body = {"email": "staff@example.com", "password": "synthetic-password",
            "locale": "es", "first_name": "First", "last_name": "Last", field: value}
    result = await request(handler, "POST", "/admin/operators", user, body=body)
    assert result.status_code == 422
    assert "/admin/operators" not in calls


async def test_operator_exact_boundaries_and_trim_forwarded() -> None:
    user = profile("admin")
    body = {"email": "a" * 60 + "@" + "b" * 55 + ".com",
            "password": "synthetic-password", "locale": "es",
            "first_name": " " + "f" * 50 + " ", "last_name": " " + "l" * 50 + " "}
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/internal/introspect":
            return httpx.Response(200, json=user)
        assert req.url.path == "/admin/operators"
        assert json.loads(req.content) == dict(body, first_name="f" * 50, last_name="l" * 50)
        return httpx.Response(201, json={"ok": True})
    result = await request(handler, "POST", "/admin/operators", user, body=body)
    assert result.status_code == 201


@pytest.mark.parametrize("method,path,status", [("GET", "/internal/introspect", 404),
    ("GET", "/admin/users", 404), ("POST", "/admin/operators/user-2/delete", 404),
    ("DELETE", "/admin/operators", 405),
    ("POST", "/admin/customers", 405),
    ("DELETE", "/admin/customers", 405),
    ("POST", "/admin/customers/user-2/reset-password", 404),
    ("POST", "/admin/customers/user-2/delete", 404)])
async def test_unknown_paths_not_forwarded(method: str, path: str, status: int) -> None:
    result = await request(lambda req: pytest.fail("Unknown route forwarded"), method, path, profile("admin"))
    assert result.status_code == status


@pytest.mark.parametrize("field,value", [("role", "unknown"), ("identity_version", True),
    ("identity_version", "1"), ("identity_version", 0), ("customer_id", None),
    ("email", " "), ("iss", "wrong"), ("aud", "wrong"), ("exp", 1)])
async def test_local_claims_fail_before_http(field: str, value: Any) -> None:
    user = profile()
    result = await request(lambda req: pytest.fail("Bad JWT forwarded"), "GET", "/auth/me", user,
                           bearer=token(user, **{field: value}))
    assert result.status_code == 401


@pytest.mark.parametrize("status", [401, 500, 302, 403, 404, 429, 201, 204])
async def test_unavailable_or_inactive(status: int) -> None:
    result = await request(lambda req: httpx.Response(status), "GET", "/auth/me", profile())
    assert result.status_code == (401 if status == 401 else 503)


@pytest.mark.parametrize("field,value", [("identity_version", 2), ("customer_id", "foreign"),
    ("sub", "foreign"), ("role", "operator")])
async def test_profile_mismatch(field: str, value: Any) -> None:
    user = profile()
    current = dict(user, **{field: value})
    if field == "role":
        del current["customer_id"]
    result = await request(lambda req: httpx.Response(200, json=current), "GET", "/auth/me", user)
    assert result.status_code == 401


@pytest.mark.parametrize("data", [{}, [], {"identity_version": True}])
async def test_malformed_upstream(data: Any) -> None:
    result = await request(lambda req: httpx.Response(200, json=data), "GET", "/auth/me", profile())
    assert result.status_code == 503


async def test_timeout_fails_closed() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("synthetic", request=req)
    result = await request(handler, "GET", "/auth/me", profile())
    assert result.status_code == 503


async def test_login_invalid_credentials_controlled() -> None:
    result = await request(lambda req: httpx.Response(401, json={"detail": "sensitive upstream"}),
                           "POST", "/auth/login", body={"email": "demo@example.com", "password": "wrong"})
    assert result.status_code == 401
    assert result.json() == {"detail": {"code": "INVALID_CREDENTIALS"}}


@pytest.mark.parametrize("status", [201, 204])
@pytest.mark.parametrize("path", ["/admin/operators/user-2/activate", "/admin/customers/user-2/activate", "/admin/customers/user-2/deactivate"])
async def test_admin_preserves_success_status(status: int, path: str) -> None:
    user = profile("admin")

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/internal/introspect":
            return httpx.Response(200, json=user)
        return httpx.Response(status, json={"ok": True}) if status == 201 else httpx.Response(204)

    result = await request(handler, "POST", path, user)
    assert result.status_code == status
    if status == 201:
        assert result.json() == {"ok": True}
    else:
        assert result.content == b""


async def test_staff_profile_must_omit_customer_id() -> None:
    user = profile("operator")
    malformed = dict(user, customer_id=None)
    result = await request(lambda req: httpx.Response(200, json=malformed), "GET", "/auth/me", user)
    assert result.status_code == 503


async def test_startup_failure_closes_clients() -> None:
    configured = settings().model_copy(update={"responses_upstream_mode": "foundry"})

    def fail_credential(config: Settings) -> Any:
        raise RuntimeError("synthetic startup failure")

    app = create_app(configured, credential_factory=fail_credential)
    with pytest.raises(RuntimeError, match="synthetic startup failure"):
        async with LifespanManager(app):
            pass
    assert app.state.auth_client.is_closed
    assert app.state.http_client.is_closed


async def test_me_allows_display_name_refresh() -> None:
    user = profile()

    def handler(req: httpx.Request) -> httpx.Response:
        current = user if req.url.path == "/internal/introspect" else dict(user, name="Updated Name")
        return httpx.Response(200, json=current)

    result = await request(handler, "GET", "/auth/me", user)
    assert result.status_code == 200
    assert result.json()["name"] == "Updated Name"


async def test_invalid_json_fails_closed() -> None:
    result = await request(lambda req: httpx.Response(200, content=b"not-json"),
                           "GET", "/auth/me", profile())
    assert result.status_code == 503


@pytest.mark.parametrize("action", ["activate", "deactivate"])
@pytest.mark.parametrize("user_id", ["bad%3Aid", "bad%20id", "x" * 129])
async def test_customer_unsafe_id_not_forwarded(action: str, user_id: str) -> None:
    user = profile("admin")

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/internal/introspect"
        return httpx.Response(200, json=user)

    result = await request(handler, "POST", f"/admin/customers/{user_id}/{action}", user)
    assert result.status_code == 422


@pytest.mark.parametrize("path", ["/admin/customers", "/admin/customers/user-2/activate", "/admin/customers/user-2/deactivate"])
async def test_revoked_admin_customer_access_not_forwarded(path: str) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/internal/introspect"
        return httpx.Response(401)

    result = await request(handler, "GET" if path == "/admin/customers" else "POST", path, profile("admin"))
    assert result.status_code == 401


@pytest.mark.parametrize("status", [401, 403, 404, 409, 500])
async def test_customer_lifecycle_error_is_controlled(status: int) -> None:
    user = profile("admin")

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/internal/introspect":
            return httpx.Response(200, json=user)
        return httpx.Response(status, json={"detail": "sensitive upstream"})

    result = await request(handler, "POST", "/admin/customers/user-2/deactivate", user)
    assert result.status_code == (status if status < 500 else 503)
    assert "sensitive upstream" not in result.text
    assert isinstance(result.json()["detail"]["code"], str)
