"""Retain simulated-review history, retire catalog, bind real ownership to Operator."""
from alembic import op
from alembic.operations import BatchOperations
import sqlalchemy as sa

revision = "20261004_0010"
down_revision = "20261004_0009"
branch_labels = None
depends_on = None

NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def _drop_foreign_keys(batch: BatchOperations, table: str, column: str) -> None:
    for constraint in sa.inspect(op.get_bind()).get_foreign_keys(table):
        if column in constraint["constrained_columns"]:
            name = constraint["name"] or (
                f"fk_{table}_{column}_{constraint['referred_table']}"
            )
            batch.drop_constraint(name, type_="foreignkey")


def upgrade() -> None:
    connection = op.get_bind()
    metadata = sa.MetaData()
    cases = sa.Table("support_cases", metadata, autoload_with=connection)
    operators = sa.Table("operators", metadata, autoload_with=connection)
    orphan = connection.execute(sa.select(cases.c.case_id).select_from(
        cases.outerjoin(operators, cases.c.assigned_operator_sub == operators.c.user_id)
    ).where(cases.c.assigned_operator_sub.is_not(None), operators.c.user_id.is_(None)).limit(1)).first()
    if orphan is not None:
        raise RuntimeError("Real operator ownership must reference a persisted Operator before retirement")

    archive = op.create_table(
        "legacy_operator_service_agents",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("service_agent_id", sa.String(64), nullable=False),
    )
    connection.execute(archive.insert().from_select(
        ["user_id", "service_agent_id"],
        sa.select(operators.c.user_id, operators.c.service_agent_id).where(
            operators.c.service_agent_id.is_not(None)
        ),
    ))
    with op.batch_alter_table("support_cases", naming_convention=NAMING) as batch:
        _drop_foreign_keys(batch, "support_cases", "assigned_agent_id")
        batch.alter_column("assigned_agent_id", new_column_name="legacy_assigned_agent_id",
                           existing_type=sa.String(64), existing_nullable=True)
        batch.create_foreign_key("fk_support_cases_operator", "operators",
                                 ["assigned_operator_sub"], ["user_id"], ondelete="RESTRICT")
    with op.batch_alter_table("operators", naming_convention=NAMING) as batch:
        _drop_foreign_keys(batch, "operators", "service_agent_id")
        for constraint in sa.inspect(connection).get_unique_constraints("operators"):
            if constraint["column_names"] == ["service_agent_id"] and constraint["name"]:
                batch.drop_constraint(constraint["name"], type_="unique")
        batch.drop_column("service_agent_id")
    # Snapshots have no live FKs: deleting a dimension must not delete or rewrite history.
    with op.batch_alter_table("service_agents", naming_convention=NAMING) as batch:
        _drop_foreign_keys(batch, "service_agents", "assigned_branch_id")
    op.rename_table("service_agents", "legacy_service_agents")


def downgrade() -> None:
    raise RuntimeError("Forward-only migration preserves archived reviewer and ownership audit history")
