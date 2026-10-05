"""Adjudication migration preserves source/history and rejects unsafe duplicates."""
import importlib.util
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.fixture
def migration() -> ModuleType:
    path = Path(__file__).parents[1] / "alembic" / "versions" / "20261004_0011_operator_effects.py"
    spec = importlib.util.spec_from_file_location("operator_effects_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def connection() -> Iterator[sa.Connection]:
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    cases = sa.Table(
        "support_cases", metadata,
        sa.Column("case_id", sa.String(64), primary_key=True),
        sa.Column("transaction_id", sa.String(64)),
        sa.Column("status", sa.String(32)), sa.Column("reason", sa.String()),
    )
    transactions = sa.Table(
        "transactions", metadata,
        sa.Column("transaction_id", sa.String(64), primary_key=True),
        sa.Column("amount", sa.Numeric(20, 4)),
    )
    for table, key in (("products", "product_id"), ("customers", "customer_id"),
                       ("operators", "user_id")):
        sa.Table(table, metadata, sa.Column(key, sa.String(64), primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(transactions.insert().values(transaction_id="original", amount=12))
        connection.execute(cases.insert().values(
            case_id="legacy", transaction_id="original", status="RESOLVED", reason="Original reason",
        ))
        yield connection
    engine.dispose()


def test_effects_migration_preserves_legacy_and_source_without_retrocredits(
    migration: ModuleType, connection: sa.Connection,
) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
    cases = sa.Table("support_cases", sa.MetaData(), autoload_with=connection)
    transactions = sa.Table("transactions", sa.MetaData(), autoload_with=connection)
    legacy = connection.execute(sa.select(cases)).mappings().one()
    assert legacy["status"] == "RESOLVED" and legacy["reason"] == "Original reason"
    assert legacy["case_version"] == 0 and legacy["evidence_version"] == 0
    assert legacy["verdict"] is None and legacy["evidence_snapshot"] is None
    source = connection.execute(sa.select(transactions)).mappings().one()
    assert source["source_kind"] == "source" and source["original_transaction_id"] is None
    assert source["support_case_id"] is None and source["amount"] == 12
    postings = sa.Table("runtime_postings", sa.MetaData(), autoload_with=connection)
    assert connection.execute(sa.select(postings)).all() == []
    inspector = sa.inspect(connection)
    assert {"runtime_postings", "card_protections"} <= set(inspector.get_table_names())
    index = next(item for item in inspector.get_indexes("support_cases")
                 if item["name"] == "uq_support_cases_active_transaction")
    assert index["unique"] and index["column_names"] == ["transaction_id"]
    connection.execute(cases.insert().values(
        case_id="active", transaction_id="original", status="PENDING_EFFECTS",
    ))
    with pytest.raises(sa.exc.IntegrityError):
        connection.execute(cases.insert().values(
            case_id="duplicate", transaction_id="original", status="IN_REVIEW",
        ))
    with Operations.context(MigrationContext.configure(connection)):
        with pytest.raises(RuntimeError, match="audit"):
            migration.downgrade()


def test_effects_migration_rejects_duplicate_active_before_schema_change(
    migration: ModuleType, connection: sa.Connection,
) -> None:
    cases = sa.Table("support_cases", sa.MetaData(), autoload_with=connection)
    connection.execute(cases.insert(), [
        {"case_id": "one", "transaction_id": "original", "status": "IN_REVIEW"},
        {"case_id": "two", "transaction_id": "original", "status": "OPEN"},
    ])
    with Operations.context(MigrationContext.configure(connection)):
        with pytest.raises(RuntimeError, match="Duplicate active disputes"):
            migration.upgrade()
    assert "case_version" not in {column["name"] for column in
                                  sa.inspect(connection).get_columns("support_cases")}
    assert "runtime_postings" not in sa.inspect(connection).get_table_names()
