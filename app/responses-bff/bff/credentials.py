"""Azure credential selection for Foundry upstream calls."""

from __future__ import annotations

from azure.identity.aio import AzureCliCredential, ManagedIdentityCredential

from bff.settings import Settings


def create_azure_credential(
    settings: Settings,
) -> AzureCliCredential | ManagedIdentityCredential:
    """Create the application-lifetime credential for the active environment."""
    if settings.profile == "dev":
        return AzureCliCredential()
    return ManagedIdentityCredential(client_id=settings.azure_client_id)