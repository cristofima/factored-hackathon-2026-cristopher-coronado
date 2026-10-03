"""Auth-owned principals and associations, independent of banking customers."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, Index
from sqlmodel import Field, SQLModel

IDENTITY_ROLES = ("customer", "operator", "admin")
IDENTITY_ACTIONS = (
    "login", "operator_create", "operator_activate", "operator_deactivate",
    "operator_reset_password", "admin_bootstrap", "customer_migrate",
    "customer_activate", "customer_deactivate",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="ck_users_status"),
        CheckConstraint("identity_version >= 1", name="ck_users_identity_version"),
        CheckConstraint("email = lower(trim(email))", name="ck_users_normalized_email"),
        CheckConstraint("locale IN ('en', 'es', 'pt')", name="ck_users_locale"),
        CheckConstraint("length(email) <= 120", name="ck_users_email_length"),
        CheckConstraint("length(name) <= 101", name="ck_users_name_length"),
        Index("ix_users_status", "status"),
        Index("ix_users_identity_version", "identity_version"),
        Index("ix_users_locale", "locale"),
        Index("ix_users_name", "name"),
    )

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, max_length=36)
    email: str = Field(unique=True, index=True, max_length=120)
    password_hash: str = Field(max_length=500, repr=False)
    locale: str = Field(max_length=8)
    name: str | None = Field(default=None, max_length=101)
    status: str = Field(default="inactive", max_length=16)
    identity_version: int = Field(default=1)
    created_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Role(SQLModel, table=True):
    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint("name IN ('customer', 'operator', 'admin')", name="ck_roles_name"),
    )
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(unique=True, max_length=16)


class UserRole(SQLModel, table=True):
    __tablename__ = "user_roles"
    __table_args__ = (Index("ix_user_roles_role_user", "role_id", "user_id"),)
    user_id: str = Field(primary_key=True, foreign_key="users.id", max_length=36)
    role_id: int = Field(foreign_key="roles.id")


class CustomerUser(SQLModel, table=True):
    __tablename__ = "customer_users"
    user_id: str = Field(primary_key=True, foreign_key="users.id", max_length=36)
    customer_id: str = Field(unique=True, foreign_key="customers.customer_id", max_length=64)


class Operator(SQLModel, table=True):
    __tablename__ = "operators"
    __table_args__ = (
        CheckConstraint("length(first_name) <= 50", name="ck_operators_first_name_length"),
        CheckConstraint("length(last_name) <= 50", name="ck_operators_last_name_length"),
        Index("ix_operators_first_name", "first_name"),
        Index("ix_operators_last_name", "last_name"),
    )
    user_id: str = Field(primary_key=True, foreign_key="users.id", max_length=36)
    first_name: str | None = Field(default=None, max_length=50)
    last_name: str | None = Field(default=None, max_length=50)

    service_agent_id: str | None = Field(
        default=None, unique=True, foreign_key="service_agents.agent_id", max_length=64,
    )

    @property
    def display_name(self) -> str | None:
        return " ".join(part for part in (self.first_name, self.last_name) if part) or None


class IdentityAudit(SQLModel, table=True):
    __tablename__ = "identity_audits"
    __table_args__ = (
        CheckConstraint(
            "action IN ('login', 'operator_create', 'operator_activate', "
            "'operator_deactivate', 'operator_reset_password', 'admin_bootstrap', "
            "'customer_migrate', 'customer_activate', 'customer_deactivate')",
            name="ck_identity_audits_action",
        ),
        CheckConstraint("result IN ('success', 'denied')", name="ck_identity_audits_result"),
        Index("ix_identity_audits_action", "action"),
        Index("ix_identity_audits_result", "result"),
    )
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True, max_length=36)
    actor_id: str | None = Field(default=None, foreign_key="users.id", max_length=36)
    target_id: str = Field(foreign_key="users.id", index=True, max_length=36)
    action: str = Field(max_length=32)
    result: str = Field(default="success", max_length=16)
    occurred_at: datetime = Field(
        default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False),
    )
