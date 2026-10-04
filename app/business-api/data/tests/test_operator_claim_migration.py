"""Additive takeover migration preserves historical assignments and events."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_operator_claim_migration_preserves_history() -> None:
    path = Path(__file__).parents[1] / "alembic" / "versions" / "20261004_0009_operator_claims.py"
    spec = importlib.util.spec_from_file_location("operator_claim_revision", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    cases = sa.Table("support_cases", metadata, sa.Column("case_id", sa.String(), primary_key=True),
                     sa.Column("status", sa.String()), sa.Column("opened_at", sa.DateTime()),
                     sa.Column("assigned_agent_id", sa.String()))
    events = sa.Table("support_case_events", metadata, sa.Column("event_id", sa.String(), primary_key=True),
                      sa.Column("message", sa.String()))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(cases.insert().values(case_id="legacy", status="IN_REVIEW", assigned_agent_id="catalog"))
        connection.execute(events.insert().values(event_id="legacy-event", message="Original historical text"))
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        cases = sa.Table("support_cases", sa.MetaData(), autoload_with=connection)
        events = sa.Table("support_case_events", sa.MetaData(), autoload_with=connection)
        case = connection.execute(sa.select(cases)).mappings().one()
        assert case["assigned_agent_id"] == "catalog" and case["claim_version"] == 0
        assert case["assigned_operator_sub"] is None and case["claimed_at"] is None
        audit = connection.execute(sa.select(events)).mappings().one()
        assert audit["message"] == "Original historical text" and audit["operator_sub"] is None
        with pytest.raises(RuntimeError, match="audit history"):
            module.downgrade()
    engine.dispose()
