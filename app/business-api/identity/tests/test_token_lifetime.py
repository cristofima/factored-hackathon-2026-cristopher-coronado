"""Access-token lifetime is absolute and honors bounded explicit configuration."""
from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlmodel import Session, select

from banking_shared import IdentityAudit
from identity.main import create_app
from identity.settings import Settings


@pytest.mark.parametrize("minutes", [None, 1, 15, 60])
def test_login_issues_configured_access_lifetime(
    settings: Settings, engine: Engine, monkeypatch: pytest.MonkeyPatch,
    minutes: int | None,
) -> None:
    monkeypatch.delenv("ACCESS_TOKEN_MINUTES", raising=False)
    values = settings.model_dump(exclude={"access_token_minutes"})
    if minutes is not None:
        values["access_token_minutes"] = minutes
    configured = Settings(**values)
    expected_seconds = (60 if minutes is None else minutes) * 60
    with TestClient(create_app(configured, engine)) as client:
        response = client.post("/auth/login", json={
            "email": "customer@synthetic.invalid", "password": "synthetic-password",
        })
    assert response.status_code == 200
    body = response.json()
    claims = jwt.decode(
        body["access_token"], configured.jwt_secret_key.get_secret_value(),
        algorithms=["HS256"], issuer="synthetic", audience="synthetic",
    )
    assert body["expires_in"] == expected_seconds
    assert claims["exp"] - claims["iat"] == expected_seconds
    assert claims["identity_version"] == 1
    assert claims["customer_id"] == "synthetic-customer"
    assert "refresh_token" not in body
    with Session(engine) as session:
        audits = session.exec(select(IdentityAudit).where(IdentityAudit.action == "login")).all()
        assert len(audits) == 1


@pytest.mark.parametrize("minutes", [0, 61])
def test_access_lifetime_rejects_out_of_range(settings: Settings, minutes: int) -> None:
    values = settings.model_dump()
    values["access_token_minutes"] = minutes
    with pytest.raises(ValidationError):
        Settings(**values)


def test_access_lifetime_honors_environment_override(
    settings: Settings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACCESS_TOKEN_MINUTES", "15")
    assert Settings(**settings.model_dump(exclude={"access_token_minutes"})).access_token_minutes == 15
