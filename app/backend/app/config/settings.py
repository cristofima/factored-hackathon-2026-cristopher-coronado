import os
from typing import List
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_env_files() -> List[str]:
    """Get list of environment files to load based on current environment."""
    env = os.getenv("PROFILE")

    if env:
        print(f"Loading environment files for environment: {env}")
    else:
        print("No environment specified, environment variables only configuration will be used.")
        return []
    
    env = env.lower()
    # List of env files to try (in order of priority - later files override earlier ones)
    env_files = [
        ".env",  # Base environment file
        f".env.{env}"  # Environment-specific file
        
    ]

    final_env_files = []
    # print found env files only if path exists
    print("Environment files loading:")    
    for f in env_files:
        print(f"Loading: {f}")
        if os.path.exists(f):
            final_env_files.append(f)
            print(f"{f} Loaded")

    return final_env_files

class Settings(BaseSettings):
    """Application settings loaded from environment or environment-specific .env files.

    Settings are loaded in the following order (later sources override earlier ones):
    1. Default values defined in the class
    2. Environment variables
    3. Base .env file
    4. Environment-specific .env file (e.g., .env.development, .env.production)
    
    The environment is determined by the ENVIRONMENT environment variable or defaults to 'development'.
    """

    # app-level
    APP_NAME: str = "Home Banking Multi-Agent Assistant"
    PROFILE: str = Field(default="prod")

    #Logging and monitoring
    APPLICATIONINSIGHTS_CONNECTION_STRING: str | None = Field(default=None)
    ENABLE_OTEL : bool = Field(default=True)
  
    
    # maps to environment variables described by the user

    #Azure OpenAI Chat configuration
    AZURE_OPENAI_ENDPOINT: str | None = Field(default=None)
    AZURE_OPENAI_CHAT_DEPLOYMENT_NAME: str = Field(default="gpt-4o")

    @field_validator("AZURE_OPENAI_ENDPOINT")
    @classmethod
    def validate_azure_openai_endpoint(cls, value: str | None) -> str | None:
        if value:
            url = urlsplit(value)
            if url.path not in ("", "/") or url.query or url.fragment:
                raise ValueError(
                    "AZURE_OPENAI_ENDPOINT must be the resource root URL, "
                    "not an /openai/v1/responses or chat/completions URL"
                )
        return value

    # Azure services
    AZURE_STORAGE_ACCOUNT: str | None = Field(default=None)
    AZURE_STORAGE_CONTAINER: str | None = Field(default="content")

    #MCP servers
    ACCOUNT_MCP_URL: str | None= Field(default=None,description="MCP server URL (required)", min_length=1)
    TRANSACTION_MCP_URL: str | None= Field(default=None,description="MCP server URL (required)", min_length=1)
    PAYMENT_MCP_URL: str | None= Field(default=None,description="MCP server URL (required)", min_length=1)

    # Support for User Assigned Managed Identity: empty means system-managed
    AZURE_CLIENT_ID: str  | None = Field(default="system-managed-identity")

    model_config = SettingsConfigDict(
        env_file=get_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()