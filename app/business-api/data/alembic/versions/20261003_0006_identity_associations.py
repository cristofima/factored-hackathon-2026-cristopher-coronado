"""Add identity associations before removing the legacy customer foreign key."""
from __future__ import annotations

from collections.abc import Sequence

from alembic import context, op
from argon2 import extract_parameters
from argon2.exceptions import InvalidHashError
import sqlalchemy as sa
from sqlalchemy.engine import Connection

def association_tables(connection: Connection) -> dict[str, sa.Table]:
    """Define the approved associations independently of mutable application models."""
    metadata = sa.MetaData()
    for name in ("users", "customers", "service_agents"):
        sa.Table(name, metadata, autoload_with=connection)
    roles = sa.Table("roles", metadata,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(16), nullable=False),
        sa.UniqueConstraint("name", name="uq_roles_name"),
        sa.CheckConstraint("name IN ('customer', 'operator', 'admin')", name="ck_roles_name"))
    customers = sa.Table("customer_users", metadata,
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("customer_id", sa.String(64), sa.ForeignKey("customers.customer_id"),
                  nullable=False, unique=True))
    assignments = sa.Table("user_roles", metadata,
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), nullable=False),
        sa.Index("ix_user_roles_role_user", "role_id", "user_id"))
    operators = sa.Table("operators", metadata,
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("service_agent_id", sa.String(64), sa.ForeignKey("service_agents.agent_id"),
                  nullable=True, unique=True),
        sa.Column("first_name", sa.String(50), nullable=True),
        sa.Column("last_name", sa.String(50), nullable=True),
        sa.CheckConstraint("length(first_name) <= 50", name="ck_operators_first_name_length"),
        sa.CheckConstraint("length(last_name) <= 50", name="ck_operators_last_name_length"),
        sa.Index("ix_operators_first_name", "first_name"),
        sa.Index("ix_operators_last_name", "last_name"))
    return {table.name: table for table in (roles, customers, assignments, operators)}

revision: str = "20261003_0006"
down_revision: str | None = "20261001_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def legacy_rows(connection: Connection) -> list[sa.RowMapping]:
    metadata = sa.MetaData()
    users = sa.Table("users", metadata, autoload_with=connection)
    customers = sa.Table("customers", metadata, autoload_with=connection)
    rows = list(connection.execute(sa.select(users)).mappings())
    known = set(connection.execute(sa.select(customers.c.customer_id)).scalars())
    emails: set[str] = set()
    owners: set[str] = set()
    for row in rows:
        email = row["email"]
        if (not email or email != email.strip().lower() or "@" not in email
                or email in emails or row["customer_id"] not in known
                or row["customer_id"] in owners or row["locale"] not in {"en", "es", "pt"}
                or row["created_at"] is None):
            raise RuntimeError("Legacy identity validation failed; no identities changed")
        try:
            extract_parameters(row["password_hash"])
        except (InvalidHashError, ValueError, TypeError) as exc:
            raise RuntimeError("Legacy password hash validation failed") from exc
        emails.add(email)
        owners.add(row["customer_id"])
    return rows


LENGTHS = {
    "users": {"email": 120},
    "customers": {"email": 120, "first_name": 50, "last_name": 50, "country": 100},
}
STATUSES = ("Active", "Inactive", "Suspended", "Closed")
INDEX_FIELDS = {
    "users": ("status", "identity_version", "locale", "name"),
    "customers": ("first_name", "last_name", "country", "customer_status"),
}


def schema_preflight(connection: Connection) -> dict[str, sa.Table]:
    tables = {name: sa.Table(name, sa.MetaData(), autoload_with=connection)
              for name in LENGTHS}
    for name, fields in LENGTHS.items():
        for field, maximum in fields.items():
            if connection.execute(sa.select(tables[name].c[field]).where(
                sa.func.length(tables[name].c[field]) > maximum)).first():
                raise RuntimeError(
                    f"Schema preflight failed: {name}.{field} exceeds {maximum}"
                )
    customers = tables["customers"]
    if connection.execute(sa.select(customers.c.customer_id).where(
        customers.c.customer_status.is_not(None),
        customers.c.customer_status.not_in(STATUSES))).first():
        raise RuntimeError("Schema preflight failed: unknown customer status")
    return tables


def upgrade() -> None:
    connection = op.get_bind()
    tables_before = schema_preflight(connection)
    rows = legacy_rows(connection)
    status = context.get_x_argument(as_dictionary=True).get("legacy-user-status")
    if rows and status not in {"active", "inactive"}:
        raise RuntimeError("Explicit -x legacy-user-status=active|inactive is required")
    op.add_column("users", sa.Column("name", sa.String(101), nullable=True))
    op.add_column("users", sa.Column("status", sa.String(16), nullable=True))
    op.add_column("users", sa.Column("identity_version", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    users = sa.Table("users", sa.MetaData(), autoload_with=connection)
    connection.execute(users.update().values(
        status=status or "inactive", identity_version=1, updated_at=users.c.created_at,
    ))
    with op.batch_alter_table("users") as batch:
        batch.alter_column("status", existing_type=sa.String(16), nullable=False)
        batch.alter_column("identity_version", existing_type=sa.Integer(), nullable=False)
        batch.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.create_check_constraint("ck_users_status", "status IN ('active', 'inactive')")
        batch.create_check_constraint("ck_users_identity_version", "identity_version >= 1")
        batch.create_check_constraint("ck_users_normalized_email", "email = lower(trim(email))")
        batch.create_check_constraint("ck_users_locale", "locale IN ('en', 'es', 'pt')")
        batch.create_check_constraint("ck_users_name_length", "length(name) <= 101")
    for name, fields in LENGTHS.items():
        with op.batch_alter_table(name) as batch:
            for field, maximum in fields.items():
                batch.alter_column(field, existing_type=tables_before[name].c[field].type,
                                   type_=sa.String(maximum))
                batch.create_check_constraint(f"ck_{name}_{field}_length",
                                              f"length({field}) <= {maximum}")
            if name == "customers":
                batch.create_check_constraint("ck_customers_status",
                    "customer_status IN ('Active', 'Inactive', 'Suspended', 'Closed')")
    for name, fields in INDEX_FIELDS.items():
        for field in fields:
            op.create_index(f"ix_{name}_{field}", name, [field])
    tables = association_tables(connection)
    for table in tables.values():
        table.create(connection)
    for name in ("customer", "operator", "admin"):
        connection.execute(tables["roles"].insert().values(name=name))
    customer_role_id = connection.execute(sa.select(tables["roles"].c.id).where(
        tables["roles"].c.name == "customer")).scalar_one()
    if rows:
        connection.execute(tables["customer_users"].insert(), [
            {"user_id": row["id"], "customer_id": row["customer_id"]} for row in rows
        ])
        connection.execute(tables["user_roles"].insert(), [
            {"user_id": row["id"], "role_id": customer_role_id} for row in rows
        ])


def downgrade() -> None:
    connection = op.get_bind()
    tables = {name: sa.Table(name, sa.MetaData(), autoload_with=connection)
              for name in ("roles", "customer_users", "user_roles", "operators")}
    mappings = tables["customer_users"]
    customer_role_id = connection.execute(sa.select(tables["roles"].c.id).where(
        tables["roles"].c.name == "customer")).scalar_one_or_none()
    if customer_role_id is None:
        raise RuntimeError("Downgrade would lose identity state: missing customer role")
    users = sa.Table("users", sa.MetaData(), autoload_with=connection)
    invalid = connection.execute(sa.select(users.c.id).outerjoin(
        mappings, mappings.c.user_id == users.c.id,
    ).outerjoin(tables["user_roles"], tables["user_roles"].c.user_id == users.c.id).where(sa.or_(
        mappings.c.customer_id.is_(None), mappings.c.customer_id != users.c.customer_id,
        tables["user_roles"].c.role_id.is_(None),
        tables["user_roles"].c.role_id != customer_role_id,
        users.c.identity_version != 1,
        users.c.status != "active", users.c.name.is_not(None),
        users.c.updated_at != users.c.created_at,
    ))).first()
    if invalid or connection.execute(sa.select(tables["operators"].c.user_id)).first():
        raise RuntimeError("Downgrade would lose identity state")
    for name in ("operators", "user_roles", "customer_users", "roles"):
        tables[name].drop(connection)
    for name, fields in INDEX_FIELDS.items():
        for field in fields:
            op.drop_index(f"ix_{name}_{field}", table_name=name)
    with op.batch_alter_table("users") as batch:
        for name in ("ck_users_status", "ck_users_identity_version",
                     "ck_users_normalized_email", "ck_users_locale", "ck_users_name_length"):
            batch.drop_constraint(name, type_="check")
        for name in ("name", "status", "identity_version", "updated_at"):
            batch.drop_column(name)

    legacy_lengths = {
        "users": {"email": 320},
        "customers": {"email": 320, "first_name": 120, "last_name": 120, "country": 120},
    }
    for name, fields in legacy_lengths.items():
        with op.batch_alter_table(name) as batch:
            for field, maximum in fields.items():
                batch.drop_constraint(f"ck_{name}_{field}_length", type_="check")
                batch.alter_column(field, existing_type=sa.String(LENGTHS[name][field]),
                                   type_=sa.String(maximum))
            if name == "customers":
                batch.drop_constraint("ck_customers_status", type_="check")
