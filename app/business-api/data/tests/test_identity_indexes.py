"""Offline Identity/Customer index contracts and reversible migration replay."""
from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlmodel import SQLModel

from banking_shared.models import Customer
from .test_identity_migrations import additive, legacy, revision, run, table

SCOPED_TABLES = (
    "users", "roles", "user_roles", "customer_users", "operators", "identity_audits",
    Customer.__tablename__,
)
CHECK_FIELDS = {
    "users": {"email", "name", "locale", "status", "identity_version"},
    "roles": {"name"},
    "operators": {"first_name", "last_name"},
    "identity_audits": {"action", "result"},
    "customers": {"email", "first_name", "last_name", "country", "customer_status"},
}


def index_contract(table_: sa.Table) -> dict[str, tuple[tuple[str, ...], bool]]:
    return {index.name: (tuple(column.name for column in index.columns), bool(index.unique))
            for index in table_.indexes}


def coverage(table_: sa.Table) -> list[tuple[str, ...]]:
    keys = [tuple(column.name for column in table_.primary_key.columns)]
    keys.extend(tuple(column.name for column in constraint.columns)
                for constraint in table_.constraints if isinstance(constraint, sa.UniqueConstraint))
    keys.extend(tuple(column.name for column in index.columns) for index in table_.indexes)
    return [key for key in keys if key]


@pytest.fixture
def historical(monkeypatch: pytest.MonkeyPatch) -> Iterator[Connection]:
    engine = sa.create_engine("sqlite://")
    try:
        with engine.connect() as connection:
            paths = sorted((Path(__file__).parents[1] / "alembic" / "versions").glob("*.py"))
            for path in paths:
                module = revision(path.name)
                if module.revision == "20261003_0006":
                    monkeypatch.setattr(module.context, "get_x_argument", lambda **kwargs: {})
                    break
                run(connection, module)
            yield connection
    finally:
        engine.dispose()


def test_metadata_covers_every_check_field_without_redundant_prefixes() -> None:
    for name in SCOPED_TABLES:
        runtime = SQLModel.metadata.tables[name]
        keys = coverage(runtime)
        checked = {
            column.name for column in runtime.columns
            if any(re.search(rf"\b{re.escape(column.name)}\b", str(constraint.sqltext))
                   for constraint in runtime.constraints
                   if isinstance(constraint, sa.CheckConstraint))
        }
        assert checked == CHECK_FIELDS.get(name, set()), name
        for field in checked:
            assert any(key[0] == field for key in keys), (name, field)
        for index in runtime.indexes:
            columns = tuple(column.name for column in index.columns)
            others = keys.copy()
            others.remove(columns)
            assert not any(key[:len(columns)] == columns for key in others), (name, index.name)
    expected_fields = {
        "users": ("status", "identity_version", "locale", "name"),
        "customers": ("first_name", "last_name", "country", "customer_status"),
        "operators": ("first_name", "last_name"),
        "identity_audits": ("action", "result"),
    }
    for name, fields in expected_fields.items():
        indexes = index_contract(SQLModel.metadata.tables[name])
        for field in fields:
            assert indexes[f"ix_{name}_{field}"] == ((field,), False)
    assert index_contract(SQLModel.metadata.tables["user_roles"]) == {
        "ix_user_roles_role_user": (("role_id", "user_id"), False),
    }


def test_migration_indexes_match_runtime_and_downgrade_restores_legacy(
    historical: Connection, monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = {name: index_contract(table(historical, name)) for name in ("users", "customers")}
    first = additive(historical, monkeypatch, None)
    additive_indexes = index_contract(table(historical, "users"))
    second = revision("20261003_0007_independent_users.py")
    run(historical, second)
    for name in SCOPED_TABLES:
        assert index_contract(table(historical, name)) == index_contract(SQLModel.metadata.tables[name])
    run(historical, second, "downgrade")
    assert "identity_audits" not in sa.inspect(historical).get_table_names()
    assert index_contract(table(historical, "users")) == additive_indexes
    run(historical, first, "downgrade")
    for name, indexes in before.items():
        assert index_contract(table(historical, name)) == indexes
    assert not {"roles", "user_roles", "customer_users", "operators"}.intersection(
        sa.inspect(historical).get_table_names())
    additive(historical, monkeypatch, None)
    run(historical, second)
    for name in SCOPED_TABLES:
        assert index_contract(table(historical, name)) == index_contract(SQLModel.metadata.tables[name])


def test_rejected_cutover_transaction_preserves_indexes_and_allows_retry(
    legacy: Connection, monkeypatch: pytest.MonkeyPatch,
) -> None:
    additive(legacy, monkeypatch)
    before = {name: index_contract(table(legacy, name)) for name in ("users", "customers")}
    assignments = table(legacy, "user_roles")
    legacy.rollback()
    with pytest.raises(RuntimeError, match="cutover validation"):
        with legacy.begin():
            legacy.execute(assignments.delete())
            run(legacy, revision("20261003_0007_independent_users.py"))
    assert legacy.execute(sa.select(assignments)).one().user_id == "principal-1"
    for name, indexes in before.items():
        assert index_contract(table(legacy, name)) == indexes
    assert "identity_audits" not in sa.inspect(legacy).get_table_names()
    run(legacy, revision("20261003_0007_independent_users.py"))
    assert index_contract(table(legacy, "identity_audits")) == index_contract(
        SQLModel.metadata.tables["identity_audits"])


def test_rejected_downgrade_does_not_remove_indexes(
    legacy: Connection, monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = additive(legacy, monkeypatch)
    legacy.execute(table(legacy, "users").update().values(identity_version=2))
    legacy.commit()
    before = {name: index_contract(table(legacy, name))
              for name in SCOPED_TABLES if name != "identity_audits"}
    with pytest.raises(RuntimeError, match="lose identity state"):
        run(legacy, first, "downgrade")
    for name, indexes in before.items():
        assert index_contract(table(legacy, name)) == indexes
