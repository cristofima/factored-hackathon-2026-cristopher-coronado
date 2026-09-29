from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects import postgresql

from models import Customer
from scripts import seed_demo_users


class StubResult:
    def __init__(self, values: list[Customer]) -> None:
        self._values = values

    def all(self) -> list[Customer]:
        return self._values


class StubSession:
    def __init__(self, customers: list[Customer]) -> None:
        self._customers = customers
        self.statements: list[Any] = []
        self.commit_count = 0

    def exec(self, statement: Any) -> StubResult:
        self.statements.append(statement)
        if len(self.statements) == 1:
            return StubResult(self._customers)
        return StubResult([])

    def commit(self) -> None:
        self.commit_count += 1


def test_seedUsersSkipsUnknownCustomersAndUpsertsValidOnes(monkeypatch: Any) -> None:
    session = StubSession(
        [
            Customer(
                customer_id="C001",
                email=" First@Example.com ",
                country="Colombia",
            ),
            Customer(
                customer_id="C003",
                email="third@example.com",
                country="Brazil",
            ),
        ]
    )

    @contextmanager
    def create_stub_session() -> Iterator[StubSession]:
        yield session

    monkeypatch.setattr(seed_demo_users, "create_session", create_stub_session)

    result = seed_demo_users.seed_users(
        ("C001", "UNKNOWN", "C003"),
        None,
        "demo-test-password",
    )

    assert result.seeded_customer_ids == ("C001", "C003")
    assert result.skipped_customer_ids == ("UNKNOWN",)
    assert session.commit_count == 1
    assert len(session.statements) == 3

    upserts = session.statements[1:]
    compiled_upserts = [
        statement.compile(dialect=postgresql.dialect()) for statement in upserts
    ]
    assert [compiled.params["customer_id"] for compiled in compiled_upserts] == [
        "C001",
        "C003",
    ]
    assert compiled_upserts[0].params["email"] == "first@example.com"
    assert [compiled.params["locale"] for compiled in compiled_upserts] == ["es", "pt"]
    hashes = [compiled.params["password_hash"] for compiled in compiled_upserts]
    assert hashes[0] != hashes[1]
    assert hashes[0].split("$")[4] != hashes[1].split("$")[4]
    assert all(
        seed_demo_users.password_hasher.verify("demo-test-password", hashed_password)
        for hashed_password in hashes
    )

    for compiled in compiled_upserts:
        created_at = compiled.params["created_at"]
        assert isinstance(created_at, datetime)
        assert created_at.tzinfo == timezone.utc
        assert compiled.params["id"]
        sql = str(compiled)
        assert "ON CONFLICT (customer_id) DO UPDATE" in sql
        assert "email = excluded.email" in sql
        assert "password_hash = excluded.password_hash" in sql
        assert "locale = excluded.locale" in sql
        assert "id = excluded.id" not in sql
        assert "created_at = excluded.created_at" not in sql
        assert "DELETE" not in sql


def test_seedUsersWithOnlyUnknownCustomersCommitsNoWrites(monkeypatch: Any) -> None:
    session = StubSession([])

    @contextmanager
    def create_stub_session() -> Iterator[StubSession]:
        yield session

    monkeypatch.setattr(seed_demo_users, "create_session", create_stub_session)

    result = seed_demo_users.seed_users(("UNKNOWN",), "en", "argon2-hash")

    assert result.seeded_customer_ids == ()
    assert result.skipped_customer_ids == ("UNKNOWN",)
    assert session.commit_count == 1
    assert len(session.statements) == 1


def test_localeForCustomerUsesExplicitOverride() -> None:
    customer = Customer(
        customer_id="C001",
        email="customer@example.com",
        country="Brazil",
    )

    assert seed_demo_users.locale_for_customer(customer, "es") == "es"