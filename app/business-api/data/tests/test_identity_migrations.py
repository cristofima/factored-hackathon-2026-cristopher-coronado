"""Disposable legacy-schema migration checks; never load deployment configuration."""
from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pwdlib import PasswordHash
from sqlalchemy.engine import Connection


def revision(name: str) -> ModuleType:
    path = Path(__file__).parents[1] / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def legacy() -> Iterator[Connection]:
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    customers = sa.Table("customers", metadata,
                         sa.Column("customer_id", sa.String(64), primary_key=True),
                         sa.Column("email", sa.String(320)),
                         sa.Column("first_name", sa.String(120)),
                         sa.Column("last_name", sa.String(120)),
                         sa.Column("country", sa.String(120)),
                         sa.Column("customer_status", sa.String(64)))
    sa.Table("service_agents", metadata,
             sa.Column("agent_id", sa.String(64), primary_key=True))
    users = sa.Table(
        "users", metadata, sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("customer_id", sa.String(64), sa.ForeignKey("customers.customer_id"),
                  nullable=False),
        sa.Column("email", sa.String(320), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(500), nullable=False),
        sa.Column("locale", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("customer_id", name="uq_users_customer_id"),
    )
    metadata.create_all(engine)
    with engine.connect() as connection:
        connection.execute(customers.insert().values(customer_id="customer-1"))
        connection.execute(users.insert().values(
            id="principal-1", customer_id="customer-1", email="one@synthetic.invalid",
            password_hash=PasswordHash.recommended().hash("synthetic-migration-password"),
            locale="es", created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ))
        connection.commit()
        yield connection
    engine.dispose()


def table(connection: Connection, name: str) -> sa.Table:
    return sa.Table(name, sa.MetaData(), autoload_with=connection)


def run(connection: Connection, module: ModuleType, direction: str = "upgrade") -> None:
    with Operations.context(MigrationContext.configure(connection)):
        getattr(module, direction)()
    connection.commit()


def additive(connection: Connection, monkeypatch: pytest.MonkeyPatch,
             status: str | None = "active") -> ModuleType:
    module = revision("20261003_0006_identity_associations.py")
    monkeypatch.setattr(module.context, "get_x_argument",
                        lambda **kwargs: {"legacy-user-status": status} if status else {})
    run(connection, module)
    return module


def test_legacy_preservation_and_independent_cutover(
    legacy: Connection, monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = dict(legacy.execute(sa.select(table(legacy, "users"))).mappings().one())
    additive(legacy, monkeypatch)
    run(legacy, revision("20261003_0007_independent_users.py"))
    after = dict(legacy.execute(sa.select(table(legacy, "users"))).mappings().one())
    assert "customer_id" not in after
    assert all(after[key] == value for key, value in before.items() if key != "customer_id")
    assert after["status"] == "active" and after["identity_version"] == 1
    assert after["updated_at"] == before["created_at"]
    assert legacy.execute(sa.select(table(legacy, "customer_users"))).one() == (
        "principal-1", "customer-1")
    assert legacy.execute(sa.select(table(legacy, "user_roles"))).one() == (
        "principal-1", 1)
    audit = legacy.execute(sa.select(table(legacy, "identity_audits"))).mappings().one()
    assert audit["action"] == "customer_migrate" and audit["target_id"] == "principal-1"
    with pytest.raises(RuntimeError, match="audit history"):
        run(legacy, revision("20261003_0007_independent_users.py"), "downgrade")
    assert "customer_id" not in {c["name"] for c in sa.inspect(legacy).get_columns("users")}


@pytest.mark.parametrize("field,value", [
    ("email", " Mixed@synthetic.invalid"), ("locale", "unknown"),
    ("password_hash", "not-an-argon2-hash"), ("customer_id", "missing"),
])
def test_invalid_legacy_is_rejected_before_ddl(
    legacy: Connection, monkeypatch: pytest.MonkeyPatch, field: str, value: str,
) -> None:
    users = table(legacy, "users")
    legacy.execute(users.update().values(**{field: value}))
    legacy.commit()
    with pytest.raises(RuntimeError, match="validation failed"):
        additive(legacy, monkeypatch)
    assert "status" not in {c["name"] for c in sa.inspect(legacy).get_columns("users")}
    assert "roles" not in sa.inspect(legacy).get_table_names()


def test_explicit_status_gate_and_safe_retry(
    legacy: Connection, monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="Explicit"):
        additive(legacy, monkeypatch, None)
    additive(legacy, monkeypatch, "inactive")
    assert legacy.execute(sa.select(table(legacy, "users").c.status)).scalar_one() == "inactive"
    with pytest.raises(RuntimeError, match="lose identity state"):
        run(legacy, revision("20261003_0006_identity_associations.py"), "downgrade")


def test_cutover_validation_rejects_changed_associations(
    legacy: Connection, monkeypatch: pytest.MonkeyPatch,
) -> None:
    additive(legacy, monkeypatch)
    roles = table(legacy, "user_roles")
    legacy.execute(roles.update().values(role_id=3))
    legacy.commit()
    with pytest.raises(RuntimeError, match="cutover validation"):
        run(legacy, revision("20261003_0007_independent_users.py"))
    assert "identity_audits" not in sa.inspect(legacy).get_table_names()
    legacy.execute(roles.update().values(role_id=1))
    legacy.commit()
    run(legacy, revision("20261003_0007_independent_users.py"))


def test_empty_schema_can_downgrade_without_losing_state(
    legacy: Connection, monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy.execute(table(legacy, "users").delete())
    legacy.commit()
    first = additive(legacy, monkeypatch, None)
    second = revision("20261003_0007_independent_users.py")
    run(legacy, second)
    run(legacy, second, "downgrade")
    run(legacy, first, "downgrade")
    assert "customer_id" in {c["name"] for c in sa.inspect(legacy).get_columns("users")}
    assert "roles" not in sa.inspect(legacy).get_table_names()


def test_customer_lifecycle_constraint_preserves_identity_history(
    legacy: Connection, monkeypatch: pytest.MonkeyPatch,
) -> None:
    additive(legacy, monkeypatch)
    run(legacy, revision("20261003_0007_independent_users.py"))
    names = ("users", "customer_users", "user_roles", "identity_audits")
    before = {name: legacy.execute(sa.select(table(legacy, name))).all() for name in names}
    migration = revision("20261003_0008_customer_lifecycle_audit.py")
    run(legacy, migration)
    assert migration.down_revision == "20261003_0007"
    assert {name: legacy.execute(sa.select(table(legacy, name))).all() for name in names} == before
    audits = table(legacy, "identity_audits")
    for action in ("customer_activate", "customer_deactivate"):
        legacy.execute(audits.insert().values(
            id=action, actor_id="principal-1", target_id="principal-1",
            action=action, result="success", occurred_at=datetime.now(timezone.utc),
        ))
    legacy.commit()
    with pytest.raises(sa.exc.IntegrityError):
        legacy.execute(audits.insert().values(
            id="unsupported", target_id="principal-1", action="customer_delete",
            result="success", occurred_at=datetime.now(timezone.utc),
        ))
    legacy.rollback()
    assert set(legacy.execute(sa.select(audits.c.action)).scalars()) == {
        "customer_migrate", "customer_activate", "customer_deactivate"}
    with pytest.raises(RuntimeError, match="forward-only"):
        run(legacy, migration, "downgrade")
