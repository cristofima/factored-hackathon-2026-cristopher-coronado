"""Customer sign-in lifecycle against disposable synthetic records only."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session, select

from banking_shared import Customer, CustomerUser, IdentityAudit, Operator, User, UserRole


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("method,path", [
    ("GET", "/admin/customers"),
    ("POST", "/admin/customers/customer/activate"),
    ("POST", "/admin/customers/customer/deactivate"),
])
@pytest.mark.parametrize("role", ["customer", "operator", "missing", "invalid"])
def test_admin_required(client: TestClient, tokens: dict[str, str],
                        method: str, path: str, role: str, engine: Engine) -> None:
    response = client.request(method, path, headers=(
        {} if role == "missing" else headers(tokens.get(role, "invalid"))))
    assert response.status_code == (403 if role in tokens else 401)
    with Session(engine) as session:
        assert session.get(User, "customer").identity_version == 1
        assert not session.exec(select(IdentityAudit).where(
            IdentityAudit.action.in_(["customer_activate", "customer_deactivate"]))).all()


def test_customer_lifecycle_revokes_sessions_without_banking_changes(
    client: TestClient, tokens: dict[str, str], engine: Engine,
) -> None:
    admin = headers(tokens["admin"])
    with Session(engine) as session:
        banking_before = session.get(Customer, "synthetic-customer").model_dump()
        password_before = session.get(User, "customer").password_hash
    original = client.get("/admin/customers", headers=admin).json()
    assert len(original) == 1
    assert original[0]["sub"] == "customer"
    assert original[0]["customer_id"] == "synthetic-customer"
    assert original[0]["status"] == "active"
    assert "password_hash" not in original[0]
    assert not any(item["role"] != "customer" for item in original)
    for version, action in enumerate(["deactivate", "deactivate", "activate"], 2):
        response = client.post(f"/admin/customers/customer/{action}", headers=admin)
        assert response.status_code == 200
        profile = response.json()
        assert profile["identity_version"] == version
        assert profile["status"] == ("active" if action == "activate" else "inactive")
        assert profile["updated_at"] != original[0]["updated_at"]
        assert client.get("/auth/me", headers=headers(tokens["customer"])).status_code == 401
        if action == "deactivate":
            assert client.post("/auth/login", json={"email": "customer@synthetic.invalid",
                "password": "synthetic-password"}).status_code == 401
            assert client.get("/admin/customers", headers=admin).json()[0]["status"] == "inactive"
    login = client.post("/auth/login", json={"email": "customer@synthetic.invalid",
                                            "password": "synthetic-password"})
    assert login.status_code == 200
    assert client.get("/auth/me", headers=headers(login.json()["access_token"])).status_code == 200
    with Session(engine) as session:
        assert session.get(Customer, "synthetic-customer").model_dump() == banking_before
        assert session.get(User, "customer").password_hash == password_before
        audits = session.exec(select(IdentityAudit).where(
            IdentityAudit.action.in_(["customer_activate", "customer_deactivate"]))).all()
        assert len(audits) == 3
        assert sorted(audit.action for audit in audits) == ["customer_activate", "customer_deactivate", "customer_deactivate"]
        assert all(audit.actor_id == "admin" and audit.target_id == "customer" for audit in audits)


@pytest.mark.parametrize("target", ["missing", "admin", "operator"])
@pytest.mark.parametrize("action", ["activate", "deactivate"])
def test_wrong_target_rejected(client: TestClient, tokens: dict[str, str],
                               target: str, action: str, engine: Engine) -> None:
    response = client.post(f"/admin/customers/{target}/{action}", headers=headers(tokens["admin"]))
    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "AUTH_CUSTOMER_NOT_FOUND"}}
    with Session(engine) as session:
        assert all(user.identity_version == 1 for user in session.exec(select(User)).all())
        assert not session.exec(select(IdentityAudit).where(
            IdentityAudit.action.in_(["customer_activate", "customer_deactivate"]))).all()


@pytest.mark.parametrize("malformation", ["missing_membership", "missing_role", "operator_membership", "missing_customer"])
def test_malformed_customer_cannot_be_changed(client: TestClient, tokens: dict[str, str],
                                            engine: Engine, malformation: str) -> None:
    with Session(engine) as session:
        if malformation == "missing_membership":
            session.delete(session.get(CustomerUser, "customer"))
        elif malformation == "missing_role":
            session.delete(session.get(UserRole, "customer"))
        elif malformation == "operator_membership":
            session.add(Operator(user_id="customer"))
        else:
            membership = session.get(CustomerUser, "customer")
            membership.customer_id = "nonexistent-customer"
            session.add(membership)
        session.commit()
    response = client.post("/admin/customers/customer/deactivate", headers=headers(tokens["admin"]))
    assert response.status_code == 404
    listing = client.get("/admin/customers", headers=headers(tokens["admin"]))
    assert listing.status_code == (200 if malformation == "missing_role" else 401)
    if malformation == "missing_role":
        assert listing.json() == []
    with Session(engine) as session:
        customer = session.get(User, "customer")
        assert customer.status == "active"
        assert customer.identity_version == 1
        assert not session.exec(select(IdentityAudit).where(
            IdentityAudit.action == "customer_deactivate")).all()


@pytest.mark.parametrize("invalid_state", ["inactive", "stale", "wrong_role", "missing_role"])
def test_persisted_admin_state_is_rechecked(client: TestClient, tokens: dict[str, str],
                                          engine: Engine, invalid_state: str) -> None:
    with Session(engine) as session:
        user = session.get(User, "admin")
        if invalid_state == "inactive":
            user.status = "inactive"
        elif invalid_state == "stale":
            user.identity_version += 1
        elif invalid_state == "missing_role":
            session.delete(session.get(UserRole, "admin"))
        else:
            assignment = session.get(UserRole, "admin")
            assignment.role_id = session.get(UserRole, "operator").role_id
            session.add(assignment)
            session.add(Operator(user_id="admin"))
        session.add(user)
        session.commit()
    for method, path in [("GET", "/admin/customers"), ("POST", "/admin/customers/customer/activate")]:
        assert client.request(method, path, headers=headers(tokens["admin"])).status_code == 401
    with Session(engine) as session:
        assert session.get(User, "customer").identity_version == 1


@pytest.mark.parametrize("method,path,status", [
    ("POST", "/admin/customers", 405),
    ("POST", "/admin/customers/customer/reset-password", 404),
    ("DELETE", "/admin/customers/customer", 404),
    ("POST", "/admin/customers/bad.id/activate", 422),
])
def test_customer_route_allowlist(client: TestClient, tokens: dict[str, str],
                                 method: str, path: str, status: int) -> None:
    assert client.request(method, path, headers=headers(tokens["admin"])).status_code == status
