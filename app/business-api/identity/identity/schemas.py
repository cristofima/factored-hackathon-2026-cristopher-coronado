"""Strict counterpart contracts. Staff profiles never serialize customer_id."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

RoleName = Literal["customer", "operator", "admin"]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(RequestModel):
    email: str = Field(min_length=3, max_length=120)
    password: SecretStr = Field(min_length=1, max_length=256)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        value = value.strip().lower()
        if "@" not in value or any(char.isspace() for char in value):
            raise ValueError("Invalid email")
        return value


class AdminBootstrap(LoginRequest):
    password: SecretStr = Field(min_length=12, max_length=256)
    locale: Literal["en", "es", "pt"]
    name: str | None = Field(default=None, max_length=101)


class OperatorCreate(LoginRequest):
    password: SecretStr = Field(min_length=12, max_length=256)
    locale: Literal["en", "es", "pt"]
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def trim_name(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class PasswordReset(RequestModel):
    password: SecretStr = Field(min_length=12, max_length=256)


class IntrospectionRequest(RequestModel):
    token: SecretStr = Field(min_length=1, max_length=16384)


class UserProfile(BaseModel):
    sub: str
    email: str
    locale: Literal["en", "es", "pt"]
    role: RoleName
    identity_version: int = Field(strict=True, ge=1)
    status: Literal["active", "inactive"]
    updated_at: datetime
    name: str | None = None


class CustomerProfile(UserProfile):
    role: Literal["customer"] = "customer"
    customer_id: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: CustomerProfile | UserProfile
