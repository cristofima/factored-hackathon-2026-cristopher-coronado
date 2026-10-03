"""Validate associations, cut over independent principals, retain identity history."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import Connection


def reflected(connection: Connection, name: str) -> sa.Table:
    return sa.Table(name, sa.MetaData(), autoload_with=connection)


def audit_table(connection: Connection) -> sa.Table:
    metadata = sa.MetaData()
    sa.Table("users", metadata, autoload_with=connection)
    return sa.Table("identity_audits", metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("target_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("result", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('login', 'operator_create', 'operator_activate', 'operator_deactivate', 'operator_reset_password', 'admin_bootstrap', 'customer_migrate')", name="ck_identity_audits_action"),
        sa.CheckConstraint("result IN ('success', 'denied')", name="ck_identity_audits_result"),
        sa.Index("ix_identity_audits_action", "action"),
        sa.Index("ix_identity_audits_result", "result"))

revision: str = "20261003_0007"
down_revision: str | None = "20261003_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None



def schema_preflight(connection: Connection) -> None:
    lengths = {
        "users": {"email": 120, "name": 101},
        "customers": {"email": 120, "first_name": 50, "last_name": 50, "country": 100},
        "operators": {"first_name": 50, "last_name": 50},
    }
    for name, fields in lengths.items():
        table = reflected(connection, name)
        for field, maximum in fields.items():
            if connection.execute(sa.select(table.c[field]).where(
                sa.func.length(table.c[field]) > maximum)).first():
                raise RuntimeError(
                    f"Schema preflight failed: {name}.{field} exceeds {maximum}"
                )
    customers = reflected(connection, "customers")
    if connection.execute(sa.select(customers.c.customer_id).where(
        customers.c.customer_status.is_not(None),
        customers.c.customer_status.not_in(("Active", "Inactive", "Suspended", "Closed")),
    )).first():
        raise RuntimeError("Schema preflight failed: unknown customer status")

def upgrade() -> None:
    connection = op.get_bind()
    users = sa.Table("users", sa.MetaData(), autoload_with=connection)
    mappings = reflected(connection, "customer_users")
    assignments = reflected(connection, "user_roles")
    rows = list(connection.execute(sa.select(users)).mappings())
    mapped = dict(connection.execute(sa.select(mappings)).tuples().all())
    catalog = reflected(connection, "roles")
    catalog_names = list(connection.execute(sa.select(catalog.c.name)).scalars())
    if len(catalog_names) != 3 or set(catalog_names) != {"customer", "operator", "admin"}:
        raise RuntimeError("Identity associations failed cutover validation: invalid role catalog")
    customer_role_id = connection.execute(sa.select(catalog.c.id).where(
        catalog.c.name == "customer")).scalar_one()
    roles = dict(connection.execute(sa.select(assignments)).tuples().all())
    schema_preflight(connection)
    if (len(mapped) != len(rows) or len(roles) != len(rows)
            or any(mapped.get(row["id"]) != row["customer_id"]
                   or roles.get(row["id"]) != customer_role_id for row in rows)
            or connection.execute(sa.select(reflected(connection, "operators").c.user_id)).first()):
        raise RuntimeError("Identity associations failed cutover validation")
    audits = audit_table(connection)
    audits.create(connection)
    for row in rows:
        connection.execute(audits.insert().values(
            id=str(uuid4()), actor_id=None, target_id=row["id"], action="customer_migrate",
            result="success", occurred_at=datetime.now(timezone.utc),
        ))
    naming = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}
    with op.batch_alter_table("users", naming_convention=naming) as batch:
        batch.drop_constraint("uq_users_customer_id", type_="unique")
        foreign_keys = sa.inspect(connection).get_foreign_keys("users")
        for foreign_key in foreign_keys:
            if foreign_key["constrained_columns"] == ["customer_id"]:
                batch.drop_constraint(
                    foreign_key["name"] or "fk_users_customer_id_customers", type_="foreignkey",
                )
        batch.drop_column("customer_id")


def downgrade() -> None:
    connection = op.get_bind()
    users = sa.Table("users", sa.MetaData(), autoload_with=connection)
    mappings = reflected(connection, "customer_users")
    assignments = reflected(connection, "user_roles")
    catalog = reflected(connection, "roles")
    customer_role_id = connection.execute(sa.select(catalog.c.id).where(
        catalog.c.name == "customer")).scalar_one_or_none()
    if customer_role_id is None:
        raise RuntimeError("Downgrade cannot represent a missing customer role")
    invalid = connection.execute(sa.select(users.c.id).outerjoin(
        mappings, users.c.id == mappings.c.user_id,
    ).outerjoin(assignments, users.c.id == assignments.c.user_id).where(sa.or_(
        mappings.c.user_id.is_(None), assignments.c.role_id.is_(None),
        assignments.c.role_id != customer_role_id,
    ))).first()
    if (invalid
            or connection.execute(sa.select(reflected(connection, "operators").c.user_id)).first()
            or connection.execute(sa.select(reflected(connection, "identity_audits").c.id)).first()):
        raise RuntimeError("Downgrade cannot represent staff or discard identity audit history")
    reflected(connection, "identity_audits").drop(connection)
    op.add_column("users", sa.Column("customer_id", sa.String(64), nullable=True))
    users = sa.Table("users", sa.MetaData(), autoload_with=connection)
    for user_id, customer_id in connection.execute(sa.select(mappings)):
        connection.execute(users.update().where(users.c.id == user_id).values(customer_id=customer_id))
    with op.batch_alter_table("users") as batch:
        batch.alter_column("customer_id", existing_type=sa.String(64), nullable=False)
        batch.create_unique_constraint("uq_users_customer_id", ["customer_id"])
        batch.create_foreign_key("fk_users_customer_id_customers", "customers", ["customer_id"], ["customer_id"])
