"""Fail-closed token boundaries and atomic lifecycle persistence."""
from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session, select

from identity.main import create_app
from identity.settings import Settings
from banking_shared import IdentityAudit, User


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("role", ["operator", "admin"])
@pytest.mark.parametrize("customer_id", [None, "synthetic-customer"])
def test_staff_tokens_reject_customer_claim(
    client: TestClient, tokens: dict[str, str], settings: Settings,
    role: str, customer_id: str | None,
) -> None:
    claims = jwt.decode(tokens[role], options={"verify_signature": False})
    claims["customer_id"] = customer_id
    token = jwt.encode(claims, settings.jwt_secret_key.get_secret_value(), algorithm="HS256")
    assert client.get("/auth/me", headers=headers(token)).status_code == 401


def test_bad_signature_missing_claim_and_password_fail_closed(
    client: TestClient, tokens: dict[str, str], settings: Settings,
) -> None:
    claims = jwt.decode(tokens["customer"], options={"verify_signature": False})
    bad = jwt.encode(claims, "different-synthetic-signature-key-0000", algorithm="HS256")
    assert client.get("/auth/me", headers=headers(bad)).status_code == 401
    del claims["identity_version"]
    missing = jwt.encode(claims, settings.jwt_secret_key.get_secret_value(), algorithm="HS256")
    assert client.get("/auth/me", headers=headers(missing)).status_code == 401
    for email in ("customer@synthetic.invalid", "unknown@synthetic.invalid"):
        result = client.post("/auth/login", json={"email": email, "password": "wrong-password"})
        assert result.status_code == 401
        assert result.json() == {"detail": {"code": "AUTH_INVALID_CREDENTIALS"}}


def test_duplicates_and_non_operator_targets(
    client: TestClient, tokens: dict[str, str], engine: Engine,
) -> None:
    admin = headers(tokens["admin"])
    assert client.post("/admin/operators", headers=admin, json={
        "email": "customer@synthetic.invalid", "password": "synthetic-new-password",
        "locale": "en", "first_name": "First", "last_name": "Last",
    }).status_code == 409
    for target in ("admin", "customer", "missing"):
        assert client.post(f"/admin/operators/{target}/deactivate", headers=admin).status_code == 404
    with Session(engine) as session:
        assert len(session.exec(select(User)).all()) == 3
        assert not session.exec(select(IdentityAudit).where(
            IdentityAudit.action == "operator_create")).all()


def test_audit_failure_rolls_back_lifecycle(
    client: TestClient, tokens: dict[str, str], engine: Engine,
) -> None:
    def reject_audit(mapper: object, connection: object, target: IdentityAudit) -> None:
        if target.action == "operator_deactivate":
            raise OperationalError("synthetic audit failure", {}, Exception("synthetic"))

    event.listen(IdentityAudit, "before_insert", reject_audit)
    try:
        result = client.post("/admin/operators/operator/deactivate", headers=headers(tokens["admin"]))
    finally:
        event.remove(IdentityAudit, "before_insert", reject_audit)
    assert result.status_code == 503
    with Session(engine) as session:
        user = session.get(User, "operator")
        assert user is not None and user.status == "active" and user.identity_version == 1
        assert not session.exec(select(IdentityAudit).where(
            IdentityAudit.action == "operator_deactivate")).all()
    assert client.get("/auth/me", headers=headers(tokens["operator"])).status_code == 200


def test_application_startup_does_not_seed(engine: Engine, settings: Settings) -> None:
    with Session(engine) as session:
        before = len(session.exec(select(User)).all())
    with TestClient(create_app(settings, engine)):
        pass
    with Session(engine) as session:
        assert len(session.exec(select(User)).all()) == before


@pytest.mark.parametrize("changes", [
    {"status": "pending"}, {"identity_version": 0}, {"locale": "fr"},
    {"email": "UPPER@synthetic.invalid"},
])
def test_identity_database_constraints(engine: Engine, changes: dict[str, object]) -> None:
    with Session(engine) as session:
        user = session.get(User, "operator")
        assert user is not None
        for key, value in changes.items():
            setattr(user, key, value)
        session.add(user)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
