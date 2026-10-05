"""Validated application identity and authentication API contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AuthenticatedUser(BaseModel):
    sub: str = Field(min_length=1)
    email: str = Field(min_length=1)
    locale: str = Field(min_length=1)
    role: Literal["customer", "operator", "admin"]
    identity_version: int = Field(strict=True, ge=1)
    customer_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_role(self) -> AuthenticatedUser:
        if any(not value.strip() for value in (self.sub, self.email, self.locale)):
            raise ValueError("Empty identity")
        if self.customer_id is not None and not self.customer_id.strip():
            raise ValueError("Empty customer identity")
        if (self.role == "customer") != (self.customer_id is not None):
            raise ValueError("Invalid role association")
        return self


class UserProfile(AuthenticatedUser):
    name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_staff_customer_field(cls, data: Any) -> Any:
        if isinstance(data, dict) and data.get("role") in ("operator", "admin") and "customer_id" in data:
            raise ValueError("Staff profile must omit customer identity")
        return data


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
    user: UserProfile
