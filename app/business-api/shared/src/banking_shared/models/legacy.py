from __future__ import annotations

from sqlmodel import Field, SQLModel




class LegacyServiceAgent(SQLModel, table=True):
    """Migration-only historical catalog; never an operational reviewer."""

    __tablename__ = "legacy_service_agents"

    agent_id: str = Field(primary_key=True, max_length=64)
    employee_code: str | None = Field(default=None, max_length=64)
    assigned_branch_id: str | None = Field(default=None, max_length=64)
    agent_type: str | None = Field(default=None, max_length=64)
    experience_level: str | None = Field(default=None, max_length=64)
    languages: str | None = Field(default=None, max_length=250)
    specialty: str | None = Field(default=None, max_length=120)
    agent_status: str | None = Field(default=None, max_length=64)


class LegacyOperatorServiceAgent(SQLModel, table=True):
    """Snapshot of an obsolete association, without identity or catalog authority."""

    __tablename__ = "legacy_operator_service_agents"
    user_id: str = Field(primary_key=True, max_length=36)
    service_agent_id: str = Field(max_length=64)
