"""Configuration for the Responses BFF."""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed BFF settings."""

    app_name: str = "Banking Assistant Responses BFF"
    profile: str = "prod"
    responses_upstream_mode: Literal["local", "foundry"] = "foundry"
    responses_agent_endpoint: str = "http://127.0.0.1:8088/responses"
    responses_token_scope: str = "https://ai.azure.com/.default"
    jwt_secret_key: str | None = Field(default=None, min_length=32)
    internal_identity_secret: str | None = Field(default=None, min_length=32)
    jwt_issuer: str = "home-banking-api"
    jwt_audience: str = "home-banking-web"
    jwt_access_token_minutes: int = Field(default=15, ge=1, le=60)
    azure_client_id: str | None = None
    allowed_origins: list[str] = ["http://localhost:5170"]

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.dev"),
        env_file_encoding="utf-8",
        extra="ignore",
    )