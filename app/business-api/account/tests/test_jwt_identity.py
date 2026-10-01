"""Verification tests for the browser-facing application JWT dependency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from jwt_identity import get_jwt_customer_id

TEST_SECRET = "test-jwt-secret-key-with-at-least-32-bytes"


def _token(
    secret: str = TEST_SECRET,
    audience: str = "home-banking-web",
    issuer: str = "home-banking-api",
    customer_id: str | object = "customer-owned",
    expires_delta: timedelta = timedelta(minutes=5),
    omit_claim: str | None = None,
) -> str:
    claims = {
        "sub": "user-1",
        "customer_id": customer_id,
        "email": "demo@example.com",
        "locale": "es",
        "iss": issuer,
        "aud": audience,
        "exp": datetime.now(timezone.utc) + expires_delta,
    }
    if omit_claim:
        claims.pop(omit_claim)
    return jwt.encode(claims, secret, algorithm="HS256")


def test_valid_token_returns_customer_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)

    assert get_jwt_customer_id(f"Bearer {_token()}") == "customer-owned"


def test_missing_authorization_header_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)

    with pytest.raises(Exception) as excinfo:
        get_jwt_customer_id(None)
    assert excinfo.value.status_code == 401


def test_expired_token_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)

    with pytest.raises(Exception) as excinfo:
        get_jwt_customer_id(f"Bearer {_token(expires_delta=timedelta(minutes=-5))}")
    assert excinfo.value.status_code == 401


def test_wrong_signature_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)

    with pytest.raises(Exception) as excinfo:
        get_jwt_customer_id(f"Bearer {_token(secret='a-different-32-byte-secret-value')}")
    assert excinfo.value.status_code == 401


def test_wrong_audience_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)

    with pytest.raises(Exception) as excinfo:
        get_jwt_customer_id(f"Bearer {_token(audience='other-web')}")
    assert excinfo.value.status_code == 401


def test_missing_customer_id_claim_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_SECRET)

    with pytest.raises(Exception) as excinfo:
        get_jwt_customer_id(f"Bearer {_token(omit_claim='customer_id')}")
    assert excinfo.value.status_code == 401


def test_missing_secret_configuration_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(Exception) as excinfo:
        get_jwt_customer_id(f"Bearer {_token()}")
    assert excinfo.value.status_code == 503
