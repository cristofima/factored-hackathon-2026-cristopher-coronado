"""Offline archival fidelity and real-operator ownership migration checks."""
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection

from .test_identity_migrations import revision, run, table


@pytest.fixture
def legacy_review() -> Iterator[Connection]:
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table("branches", metadata, sa.Column("branch_id", sa.String(64), primary_key=True))
    sa.Table("service_agents", metadata,
             sa.Column("agent_id", sa.String(64), primary_key=True),
             sa.Column("assigned_branch_id", sa.String(64), sa.ForeignKey("branches.branch_id")),
             sa.Column("specialty", sa.String(120)))
    sa.Table("operators", metadata, sa.Column("user_id", sa.String(36), primary_key=True),
             sa.Column("service_agent_id", sa.String(64), sa.ForeignKey("service_agents.agent_id"),
                       unique=True))
    sa.Table("support_cases", metadata, sa.Column("case_id", sa.String(36), primary_key=True),
             sa.Column("assigned_agent_id", sa.String(64), sa.ForeignKey("service_agents.agent_id")),
             sa.Column("assigned_operator_sub", sa.String(36)),
             sa.Column("claim_version", sa.Integer, nullable=False),
             sa.Column("claimed_at", sa.DateTime))
    sa.Table("support_case_events", metadata,
             sa.Column("event_id", sa.String(36), primary_key=True),
             sa.Column("message", sa.String), sa.Column("operator_sub", sa.String(36)))
    metadata.create_all(engine)
    with engine.connect() as connection:
        connection.execute(table(connection, "branches").insert().values(branch_id="branch"))
        connection.execute(table(connection, "service_agents").insert().values(
            agent_id="simulated", assigned_branch_id="branch", specialty="Original specialty"))
        connection.execute(table(connection, "operators").insert().values(
            user_id="real", service_agent_id="simulated"))
        connection.execute(table(connection, "support_cases").insert(), [
            {"case_id": "legacy", "assigned_agent_id": "simulated", "assigned_operator_sub": None,
             "claim_version": 0},
            {"case_id": "claimed", "assigned_agent_id": "simulated", "assigned_operator_sub": "real",
             "claim_version": 2},
        ])
        connection.execute(table(connection, "support_case_events").insert().values(
            event_id="audit", message="Unmodified historical text", operator_sub="real"))
        connection.commit()
        yield connection
    engine.dispose()


def test_retirement_archives_without_converting_simulated_ownership(legacy_review: Connection) -> None:
    catalog = dict(legacy_review.execute(sa.select(table(legacy_review, "service_agents"))).mappings().one())
    audit = dict(legacy_review.execute(sa.select(table(legacy_review, "support_case_events"))).mappings().one())
    run(legacy_review, revision("20261004_0010_retire_service_agents.py"))
    assert "service_agents" not in sa.inspect(legacy_review).get_table_names()
    assert dict(legacy_review.execute(sa.select(table(legacy_review, "legacy_service_agents"))).mappings().one()) == catalog
    assert tuple(legacy_review.execute(sa.select(table(legacy_review, "legacy_operator_service_agents"))).one()) == ("real", "simulated")
    assert "service_agent_id" not in table(legacy_review, "operators").c
    cases = table(legacy_review, "support_cases")
    rows = {row["case_id"]: row for row in legacy_review.execute(sa.select(cases)).mappings()}
    assert rows["legacy"]["legacy_assigned_agent_id"] == "simulated"
    assert rows["legacy"]["assigned_operator_sub"] is None
    assert rows["claimed"]["assigned_operator_sub"] == "real"
    assert rows["claimed"]["claim_version"] == 2
    assert dict(legacy_review.execute(sa.select(table(legacy_review, "support_case_events"))).mappings().one()) == audit
    assert sa.inspect(legacy_review).get_foreign_keys("legacy_service_agents") == []
    assert sa.inspect(legacy_review).get_foreign_keys("legacy_operator_service_agents") == []
    legacy_review.exec_driver_sql("PRAGMA foreign_keys=ON")
    with pytest.raises(sa.exc.IntegrityError):
        legacy_review.execute(table(legacy_review, "operators").delete())
    legacy_review.rollback()
    with pytest.raises(sa.exc.IntegrityError):
        legacy_review.execute(cases.update().where(cases.c.case_id == "legacy").values(assigned_operator_sub="missing"))
    legacy_review.rollback()
    with pytest.raises(RuntimeError, match="Forward-only"):
        run(legacy_review, revision("20261004_0010_retire_service_agents.py"), "downgrade")


def test_orphan_operator_stops_before_archival_ddl(legacy_review: Connection) -> None:
    cases = table(legacy_review, "support_cases")
    legacy_review.execute(cases.update().where(cases.c.case_id == "claimed").values(assigned_operator_sub="missing"))
    legacy_review.commit()
    with pytest.raises(RuntimeError, match="persisted Operator"):
        run(legacy_review, revision("20261004_0010_retire_service_agents.py"))
    assert "legacy_service_agents" not in sa.inspect(legacy_review).get_table_names()
    assert "legacy_operator_service_agents" not in sa.inspect(legacy_review).get_table_names()
    assert "assigned_agent_id" in table(legacy_review, "support_cases").c
