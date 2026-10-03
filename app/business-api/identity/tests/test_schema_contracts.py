"""Offline request, storage, and profile schema regression checks."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from banking_shared import Customer, Operator, Role, User, UserRole
from identity.schemas import AdminBootstrap, OperatorCreate


@pytest.mark.parametrize("field,value", [
    ("first_name", None), ("last_name", None), ("first_name", " "),
    ("last_name", "\t"), ("first_name", "a" * 51), ("last_name", "a" * 51),
    ("email", "a" * 113 + "@invalid"),
])
def test_operator_request_rejects_invalid_components(field: str, value: str | None) -> None:
    payload = {"email": "new@synthetic.invalid", "password": "synthetic-password",
               "locale": "en", "first_name": "First", "last_name": "Last"}
    if value is None:
        payload.pop(field)
    else:
        payload[field] = value
    with pytest.raises(ValidationError):
        OperatorCreate.model_validate(payload)


def test_name_boundaries_and_admin_optional_name() -> None:
    request = OperatorCreate(email="a" * 112 + "@invalid", password="synthetic-password",
                             locale="en", first_name="  " + "a" * 50,
                             last_name="b" * 50 + "  ")
    assert len(request.email) == 120 and len(request.name) == 101
    assert request.first_name == "a" * 50 and request.last_name == "b" * 50
    assert AdminBootstrap(email="admin@synthetic.invalid", password="synthetic-password",
                          locale="en").name is None
    with pytest.raises(ValidationError):
        AdminBootstrap(email="admin@synthetic.invalid", password="synthetic-password",
                       locale="en", name="a" * 102)


@pytest.mark.parametrize("model,identifier,field,value", [
    (User, "customer", "email", "a" * 121), (User, "customer", "name", "a" * 102),
    (Customer, "synthetic-customer", "email", "a" * 121),
    (Customer, "synthetic-customer", "first_name", "a" * 51),
    (Customer, "synthetic-customer", "last_name", "a" * 51),
    (Customer, "synthetic-customer", "country", "a" * 101),
    (Customer, "synthetic-customer", "customer_status", "unknown"),
    (Operator, "operator", "first_name", "a" * 51),
    (Operator, "operator", "last_name", "a" * 51),
])
def test_database_rejects_invalid_fields(
    engine: Engine, model: type[User] | type[Customer] | type[Operator],
    identifier: str, field: str, value: str,
) -> None:
    with Session(engine) as session:
        record = session.get(model, identifier)
        assert record is not None
        setattr(record, field, value)
        session.add(record)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


@pytest.mark.parametrize("name", ["customer", "unknown", "Customer"])
def test_role_catalog_unique_and_closed(engine: Engine, name: str) -> None:
    with Session(engine) as session:
        session.add(Role(name=name))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_single_membership(engine: Engine) -> None:
    with Session(engine) as session:
        assignment = session.get(UserRole, "customer")
        assert assignment is not None
        role_id = assignment.role_id
    with Session(engine) as session:
        session.add(UserRole(user_id="customer", role_id=role_id))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


@pytest.mark.parametrize("status", [None, "Active", "Inactive", "Suspended", "Closed"])
def test_customer_status_does_not_change_login(
    engine: Engine, client: TestClient, status: str | None,
) -> None:
    with Session(engine) as session:
        customer = session.get(Customer, "synthetic-customer")
        assert customer is not None
        customer.customer_status = status
        session.add(customer)
        session.commit()
    response = client.post("/auth/login", json={"email": "customer@synthetic.invalid",
                                               "password": "synthetic-password"})
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "customer"


def test_legacy_operator_display_fallback(engine: Engine, client: TestClient) -> None:
    with Session(engine) as session:
        user = session.get(User, "operator")
        assert user is not None
        user.name = "Unsplit legacy display"
        session.add(user)
        session.commit()
    payload = {"email": "operator@synthetic.invalid", "password": "synthetic-password"}
    assert client.post("/auth/login", json=payload).json()["user"]["name"] == "Unsplit legacy display"
    with Session(engine) as session:
        operator = session.get(Operator, "operator")
        assert operator is not None
        assert operator.first_name is None and operator.last_name is None
        operator.first_name, operator.last_name = "Given", "Family"
        session.add(operator)
        session.commit()
    assert client.post("/auth/login", json=payload).json()["user"]["name"] == "Given Family"
