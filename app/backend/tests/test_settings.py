"""Configuration checks for the Azure OpenAI chat endpoint."""

import pytest
from pydantic import ValidationError

from app.config.settings import Settings


@pytest.mark.parametrize("path", ["", "/"])
def test_azure_openai_resource_root_is_accepted(path: str) -> None:
    endpoint = f"https://example.services.ai.azure.com{path}"

    settings = Settings(AZURE_OPENAI_ENDPOINT=endpoint, _env_file=None)

    assert settings.AZURE_OPENAI_ENDPOINT == endpoint


@pytest.mark.parametrize("path", ["/openai/v1/responses", "/openai/v1/chat/completions"])
def test_azure_openai_api_route_is_rejected(path: str) -> None:
    with pytest.raises(ValidationError, match="resource root URL"):
        Settings(
            AZURE_OPENAI_ENDPOINT=f"https://example.services.ai.azure.com{path}",
            _env_file=None,
        )