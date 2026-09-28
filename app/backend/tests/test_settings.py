"""Configuration checks for the Microsoft Foundry model client."""

from app.config.settings import Settings


def test_foundry_model_configuration_is_loaded() -> None:
    settings = Settings(
        FOUNDRY_PROJECT_ENDPOINT="https://example.services.ai.azure.com/api/projects/example",
        MODEL_DEPLOYMENT_NAME="gpt-4.1-mini",
        _env_file=None,
    )

    assert settings.FOUNDRY_PROJECT_ENDPOINT == (
        "https://example.services.ai.azure.com/api/projects/example"
    )
    assert settings.MODEL_DEPLOYMENT_NAME == "gpt-4.1-mini"