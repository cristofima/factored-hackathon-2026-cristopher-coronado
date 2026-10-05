"""Authentication contract, live revocation, and administrator boundaries."""
from __future__ import annotations

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

from identity.services.bootstrap import bootstrap_admin
from identity.models.schemas import AdminBootstrap
from identity.services.service import IdentityService
from identity.settings import Settings
from banking_shared import CustomerUser, IdentityAudit, Operator, Role, User, UserRole


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("role", ["customer", "operator", "admin"])
def test_claims_and_profiles(client: TestClient, tokens: dict[str, str],
                             settings: Settings, role: str) -> None:
    claims = jwt.decode(tokens[role], settings.jwt_secret_key.get_secret_value(),
                        algorithms=["HS256"], issuer="synthetic", audience="synthetic")
    assert claims["role"] == role
    assert "status" not in claims
    assert "updated_at" not in claims
    assert type(claims["identity_version"]) is int
    assert ("customer_id" in claims) == (role == "customer")
    profile = client.get("/auth/me", headers=headers(tokens[role]))
    assert profile.status_code == 200
    assert profile.json()["status"] == "active"
    assert isinstance(profile.json()["updated_at"], str)
    assert ("customer_id" in profile.json()) == (role == "customer")
    response = client.post("/internal/introspect", headers=headers("i" * 40),
                           json={"token": tokens[role]})
    assert response.json() == profile.json()


@pytest.mark.parametrize("change", [
    {"role": "arbitrary"}, {"identity_version": True}, {"identity_version": "1"},
    {"identity_version": 2}, {"customer_id": "foreign"}, {"email": "different@invalid"},
    {"locale": "pt"}, {"iss": "wrong"}, {"aud": "wrong"}, {"exp": 1},
])
def test_invalid_claims_fail_closed(client: TestClient, tokens: dict[str, str],
                                    settings: Settings, change: dict[str, object]) -> None:
    claims = jwt.decode(tokens["customer"], options={"verify_signature": False})
    claims.update(change)
    token = jwt.encode(claims, settings.jwt_secret_key.get_secret_value(), algorithm="HS256")
    response = client.get("/auth/me", headers=headers(token))
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_internal_secret_and_admin_boundary(client: TestClient, tokens: dict[str, str]) -> None:
    for token in ("", "wrong", tokens["admin"]):
        assert client.post("/internal/introspect", headers=headers(token),
                           json={"token": tokens["customer"]}).status_code == 401
    for role in ("customer", "operator"):
        assert client.get("/admin/operators", headers=headers(tokens[role])).status_code == 403
        assert client.post("/admin/operators/operator/deactivate",
                           headers=headers(tokens[role])).status_code == 403
    assert client.get("/auth/me").status_code == 401


def test_operator_lifecycle_revokes_immediately(client: TestClient, tokens: dict[str, str],
                                               engine: Engine) -> None:
    admin = headers(tokens["admin"])
    request = {"email": " New@Synthetic.Invalid ", "password": "new-synthetic-password",
               "locale": "pt", "first_name": " Synthetic ", "last_name": " Operator "}
    assert client.post("/admin/operators", headers=admin,
                       json={**request, "role": "admin"}).status_code == 422
    created = client.post("/admin/operators", headers=admin, json=request)
    assert created.status_code == 201
    user_id = created.json()["sub"]
    assert created.json()["status"] == "inactive"
    assert isinstance(created.json()["updated_at"], str)
    assert "customer_id" not in created.json()
    assert client.post("/auth/login", json={"email": request["email"],
                                           "password": request["password"]}).status_code == 401
    assert client.post(f"/admin/operators/{user_id}/activate", headers=admin).status_code == 200
    token = client.post("/auth/login", json={"email": request["email"],
                                            "password": request["password"]}).json()["access_token"]
    assert client.post(f"/admin/operators/{user_id}/reset-password", headers=admin,
                       json={"password": "changed-synthetic-password"}).status_code == 200
    assert client.post("/internal/introspect", headers=headers("i" * 40),
                       json={"token": token}).status_code == 401
    assert client.post("/auth/login", json={"email": request["email"],
                                           "password": request["password"]}).status_code == 401
    new_token = client.post("/auth/login", json={"email": request["email"],
                                                "password": "changed-synthetic-password"}).json()[
        "access_token"]
    assert client.post(f"/admin/operators/{user_id}/deactivate", headers=admin).status_code == 200
    assert client.get("/auth/me", headers=headers(new_token)).status_code == 401
    assert client.post(f"/admin/operators/{user_id}/activate", headers=admin).status_code == 200
    assert client.get("/auth/me", headers=headers(new_token)).status_code == 401
    with Session(engine) as session:
        user = session.get(User, user_id)
        assert user is not None and user.identity_version == 5
        assert user.updated_at > user.created_at
        audits = session.exec(select(IdentityAudit).where(IdentityAudit.target_id == user_id)).all()
        assert {audit.action for audit in audits} >= {
            "operator_create", "operator_activate", "operator_deactivate", "operator_reset_password"}
        assert all("password_hash" not in audit.model_dump() for audit in audits)


@pytest.mark.parametrize("mutation", ["inactive", "no_role", "foreign_profile", "no_operator"])
def test_persisted_state_checked_each_time(client: TestClient, tokens: dict[str, str],
                                          engine: Engine, mutation: str) -> None:
    role = "operator" if mutation == "no_operator" else "customer"
    assert client.get("/auth/me", headers=headers(tokens[role])).status_code == 200
    with Session(engine) as session:
        if mutation == "inactive":
            user = session.get(User, role)
            assert user is not None
            user.status = "inactive"
            session.add(user)
        elif mutation == "no_role":
            assignment = session.get(UserRole, role)
            assert assignment is not None
            session.delete(assignment)
        elif mutation == "no_operator":
            operator = session.get(Operator, role)
            assert operator is not None
            session.delete(operator)
        else:
            session.add(Operator(user_id=role))
        session.commit()
    assert client.get("/auth/me", headers=headers(tokens[role])).status_code == 401


def test_unavailable_database_fails_closed(client: TestClient, tokens: dict[str, str],
                                          engine: Engine) -> None:
    User.__table__.drop(engine)
    response = client.get("/auth/me", headers=headers(tokens["customer"]))
    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "AUTH_UNAVAILABLE"}}


def test_bootstrap_is_explicit_and_single_admin(engine: Engine, settings: Settings) -> None:
    service = IdentityService(settings)
    request = AdminBootstrap(email="first@synthetic.invalid", password="bootstrap-synthetic",
                             locale="en")
    with Session(engine) as session:
        with pytest.raises(ValueError, match="already exists"):
            bootstrap_admin(session, service, request)
        assignment = session.get(UserRole, "admin")
        assert assignment is not None
        session.delete(assignment)
        session.commit()
        user_id = bootstrap_admin(session, service, request)
        user = session.get(User, user_id)
        assert user is not None and user.status == "active"
        assert session.get(CustomerUser, user_id) is None
        assert session.get(Role, session.get(UserRole, user_id).role_id).name == "admin"
        assert session.exec(select(IdentityAudit).where(
            IdentityAudit.target_id == user_id)).one().action == "admin_bootstrap"
