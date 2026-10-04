"""Synthetic application JWT revocation and customer-role boundary regressions."""
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import Mock

import httpx
import jwt
import pytest
from fastapi import FastAPI, HTTPException

import dispute_routers
import jwt_identity

pytestmark = pytest.mark.asyncio

SECRET = "synthetic-signing-secret-at-least-32-bytes"


def claims() -> dict[str, Any]:
    return {"sub": "user-1", "customer_id": "customer-1", "email": "demo@example.com",
            "locale": "es", "role": "customer", "identity_version": 1,
            "iss": "home-banking-api", "aud": "home-banking-web",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", SECRET)
    monkeypatch.setenv("AUTH_INTERNAL_SECRET", "synthetic-internal-secret")
    monkeypatch.setenv("JWT_ISSUER", "home-banking-api")
    monkeypatch.setenv("JWT_AUDIENCE", "home-banking-web")


def transport(monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    monkeypatch.setattr(jwt_identity, "_auth_client", lambda: httpx.AsyncClient(
        base_url="http://auth", timeout=3, transport=httpx.MockTransport(handler)))


async def invoke(payload: dict[str, Any], secret: str = SECRET) -> str:
    return await jwt_identity.get_jwt_customer_id("Bearer " + jwt.encode(payload, secret, algorithm="HS256"))


async def test_customer_introspected_each_time(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    profile = {k: v for k, v in claims().items() if k not in ("iss", "aud", "exp")}
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer synthetic-internal-secret"
        assert request.url.path == "/internal/introspect"
        assert request.extensions["timeout"]["read"] == 3
        assert set(__import__("json").loads(request.content)) == {"token"}
        calls.append(request)
        return httpx.Response(200, json=profile)
    transport(monkeypatch, handler)
    assert await invoke(claims()) == "customer-1"
    assert await invoke(claims()) == "customer-1"
    assert len(calls) == 2


@pytest.mark.parametrize("field,value", [("role", "operator"), ("role", "admin"),
    ("identity_version", True), ("identity_version", "1"), ("identity_version", 0),
    ("customer_id", ""), ("customer_id", None), ("email", " "),
    ("iss", "foreign"), ("aud", "foreign"), ("exp", 1)])
async def test_invalid_claims_rejected_before_http(monkeypatch: pytest.MonkeyPatch, field: str, value: Any) -> None:
    transport(monkeypatch, lambda request: pytest.fail("Invalid JWT must not reach Auth"))
    payload = claims()
    payload[field] = value
    with pytest.raises(HTTPException) as error:
        await invoke(payload)
    assert error.value.status_code == 401
    assert error.value.headers == {"WWW-Authenticate": "Bearer"}


@pytest.mark.parametrize("field", jwt_identity.REQUIRED_CLAIMS)
async def test_missing_claim(monkeypatch: pytest.MonkeyPatch, field: str) -> None:
    transport(monkeypatch, lambda request: pytest.fail("Missing claim reached Auth"))
    payload = claims()
    del payload[field]
    with pytest.raises(HTTPException) as error:
        await invoke(payload)
    assert error.value.status_code == 401


async def test_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    transport(monkeypatch, lambda request: pytest.fail("Bad signature reached Auth"))
    with pytest.raises(HTTPException) as error:
        await invoke(claims(), "another-synthetic-secret-32-bytes-long")
    assert error.value.status_code == 401


@pytest.mark.parametrize("status", [401, 500, 403, 302])
async def test_introspection_status(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    transport(monkeypatch, lambda request: httpx.Response(status))
    with pytest.raises(HTTPException) as error:
        await invoke(claims())
    assert error.value.status_code == (401 if status == 401 else 503)


@pytest.mark.parametrize("field,value", [("identity_version", 2), ("customer_id", "foreign"),
    ("sub", "foreign"), ("locale", "pt"), ("email", "other@example.com")])
async def test_identity_mismatch(monkeypatch: pytest.MonkeyPatch, field: str, value: Any) -> None:
    profile = {k: v for k, v in claims().items() if k not in ("iss", "aud", "exp")}
    profile[field] = value
    transport(monkeypatch, lambda request: httpx.Response(200, json=profile))
    with pytest.raises(HTTPException) as error:
        await invoke(claims())
    assert error.value.status_code == 401


@pytest.mark.parametrize("body", [{}, [], {"identity_version": True}])
async def test_malformed_profile(monkeypatch: pytest.MonkeyPatch, body: Any) -> None:
    transport(monkeypatch, lambda request: httpx.Response(200, json=body))
    with pytest.raises(HTTPException) as error:
        await invoke(claims())
    assert error.value.status_code == 503


async def test_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("synthetic", request=request)
    transport(monkeypatch, handler)
    with pytest.raises(HTTPException) as error:
        await invoke(claims())
    assert error.value.status_code == 503


@pytest.mark.parametrize("header", [None, "Basic no", "Bearer ", "garbage"])
async def test_missing_bearer(header: str | None) -> None:
    with pytest.raises(HTTPException) as error:
        await jwt_identity.get_jwt_customer_id(header)
    assert error.value.status_code == 401


@pytest.mark.parametrize("key", ["JWT_SECRET_KEY", "AUTH_INTERNAL_SECRET"])
async def test_unconfigured(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    monkeypatch.delenv(key)
    with pytest.raises(HTTPException) as error:
        await invoke(claims())
    assert error.value.status_code == 503


async def test_revocation_between_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    profile = {k: v for k, v in claims().items() if k not in ("iss", "aud", "exp")}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=profile) if calls == 1 else httpx.Response(401)

    transport(monkeypatch, handler)
    assert await invoke(claims()) == "customer-1"
    with pytest.raises(HTTPException) as error:
        await invoke(claims())
    assert error.value.status_code == 401
    assert calls == 2


async def test_invalid_json_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    transport(monkeypatch, lambda request: httpx.Response(200, content=b"not-json"))
    with pytest.raises(HTTPException) as error:
        await invoke(claims())
    assert error.value.status_code == 503


DISPUTE_REQUESTS = [
    ("GET", "", None, "list_cases"),
    (
        "POST", "", {"transactionId": "tx-1", "reason": "Unrecognized purchase"},
        "open_transaction_dispute",
    ),
    ("GET", "/case-1", None, "get_case"),
    ("GET", "/case-1/timeline", None, "get_case_timeline"),
    ("POST", "/case-1/approval", {"approved": True}, "respond_to_approval"),
    ("POST", "/case-1/resolve", {"resolutionOutcome": "DECLINED"}, "resolve_case"),
    ("POST", "/case-1/recommendation/dismiss", None, "dismiss_recommendation"),
]


def dispute_app(monkeypatch: pytest.MonkeyPatch) -> tuple[FastAPI, Mock]:
    app = FastAPI()
    app.include_router(dispute_routers.router, prefix="/api/support-cases")
    service = Mock()
    monkeypatch.setattr(dispute_routers, "service", service)
    return app, service


@pytest.mark.parametrize("method,path,body,service_method", DISPUTE_REQUESTS)
@pytest.mark.parametrize("role", ["operator", "admin"])
@pytest.mark.parametrize("customer_claim", [False, True])
async def test_staff_cannot_enter_customer_dispute_routes(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    service_method: str,
    role: str,
    customer_claim: bool,
) -> None:
    app, service = dispute_app(monkeypatch)
    transport(monkeypatch, lambda request: pytest.fail("Staff JWT reached introspection"))
    payload = claims()
    payload["role"] = role
    if not customer_claim:
        del payload["customer_id"]
    token = jwt.encode(payload, SECRET, algorithm="HS256")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://transaction"
    ) as client:
        response = await client.request(
            method, "/api/support-cases" + path, json=body,
            headers={"Authorization": "Bearer " + token},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "AUTH_REQUIRED"}}
    assert response.headers["www-authenticate"] == "Bearer"
    getattr(service, service_method).assert_not_called()
    assert service.mock_calls == []


@pytest.mark.parametrize("method,path,body,service_method", DISPUTE_REQUESTS)
@pytest.mark.parametrize("change", ["operator", "admin", "version", "revoked", "outage"])
async def test_dispute_routes_recheck_identity_before_every_service_call(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    service_method: str,
    change: str,
) -> None:
    app, service = dispute_app(monkeypatch)
    getattr(service, service_method).return_value = {
        "caseId": "case-1", "transactionId": "tx-1", "reason": "Unrecognized purchase",
        "status": "WAITING_USER_APPROVAL", "openedAt": "2026-10-01T00:00:00Z",
        "updatedAt": "2026-10-01T00:00:00Z",
    }
    payload = claims()
    profile = {key: value for key, value in payload.items() if key not in ("iss", "aud", "exp")}
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json=profile)
        if change == "revoked":
            return httpx.Response(401)
        if change == "outage":
            raise httpx.ReadTimeout("Synthetic Identity outage", request=request)
        current = dict(profile)
        if change == "version":
            current["identity_version"] = 2
        else:
            current["role"] = change
        return httpx.Response(200, json=current)

    transport(monkeypatch, handler)
    token = jwt.encode(payload, SECRET, algorithm="HS256")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://transaction"
    ) as client:
        first = await client.request(
            method, "/api/support-cases" + path, json=body,
            headers={"Authorization": "Bearer " + token},
        )
        assert first.status_code == (201 if method == "POST" and not path else 200)
        getattr(service, service_method).assert_called_once()
        service.reset_mock()
        second = await client.request(
            method, "/api/support-cases" + path, json=body,
            headers={"Authorization": "Bearer " + token},
        )

    assert second.status_code == (503 if change == "outage" else 401)
    code = "SERVICE_UNAVAILABLE" if change == "outage" else "AUTH_REQUIRED"
    assert second.json() == {"detail": {"code": code}}
    if change != "outage":
        assert second.headers["www-authenticate"] == "Bearer"
    assert calls == 2
    assert service.mock_calls == []
