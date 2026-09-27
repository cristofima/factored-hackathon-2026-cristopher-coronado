"""Dependency injection container configuration."""

from dependency_injector import containers, providers
from azure.storage.blob import BlobServiceClient

from app.helpers.blob_proxy import BlobStorageProxy
from app.config.azure_credential import get_azure_credential
from app.config.settings import settings

#Azure Chat based agents for handoff with ChatKit protocol
from app.agents.azure_chat.handoff_orchestrator import HandoffOrchestrator as HandoffOrchestratorChatKit
from app.agents.azure_chat.account_agent import AccountAgent as AccountAgentChatKit
from app.agents.azure_chat.transaction_agent import TransactionHistoryAgent as TransactionHistoryAgentChatKit
from app.agents.azure_chat.payment_agent import PaymentAgent as PaymentAgentChatKit

from agent_framework.openai import OpenAIChatCompletionClient




class Container(containers.DeclarativeContainer):
    """IoC container for application dependencies."""

    # Helpers
    blob_service_client = providers.Singleton(
        BlobServiceClient,
        credential = providers.Factory(get_azure_credential),
        account_url = f"https://{settings.AZURE_STORAGE_ACCOUNT}.blob.core.windows.net"
    )

    blob_proxy = providers.Singleton(
        BlobStorageProxy,
        client = blob_service_client,
        container_name = settings.AZURE_STORAGE_CONTAINER
    )

    # Azure Chat based agents. Unfortunately we can't create reusable singleton instance of OpenAIChatCompletionClient as it does not support token expiration management.
    _azure_chat_client = providers.Factory(
        OpenAIChatCompletionClient,
        credential=providers.Factory(get_azure_credential), 
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,model=settings.AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
    )

    #Account Agent with Azure chat based agents. Must be Factory (not Singleton) so a fresh OpenAIChatCompletionClient with valid credentials is created per request.
    account_agent_chatkit = providers.Factory(
    AccountAgentChatKit,
    azure_chat_client=_azure_chat_client,
    account_mcp_server_url=f"{settings.ACCOUNT_MCP_URL.removesuffix('/mcp')}/mcp"
    )

    transaction_agent_chatkit = providers.Factory(
    TransactionHistoryAgentChatKit,
    azure_chat_client=_azure_chat_client,
    account_mcp_server_url=f"{settings.ACCOUNT_MCP_URL.removesuffix('/mcp')}/mcp",
    transaction_mcp_server_url=f"{settings.TRANSACTION_MCP_URL.removesuffix('/mcp')}/mcp"
    )

    payment_agent_chatkit = providers.Factory(
    PaymentAgentChatKit,
    azure_chat_client=_azure_chat_client,
    account_mcp_server_url=f"{settings.ACCOUNT_MCP_URL.removesuffix('/mcp')}/mcp",
    transaction_mcp_server_url=f"{settings.TRANSACTION_MCP_URL.removesuffix('/mcp')}/mcp",
    payment_mcp_server_url=f"{settings.PAYMENT_MCP_URL.removesuffix('/mcp')}/mcp"
    )

    # A specialized chatkit Supervisor Agent implemented using agent framework handoff built-in orchestration with Azure chat based agents. 
    # A per request instance is created as based on recommendation from agent framework team about managing workflow instance.
    handoff_orchestrator_chatkit = providers.Factory(
        HandoffOrchestratorChatKit,
        azure_chat_client=_azure_chat_client,
        account_agent=account_agent_chatkit,
        transaction_agent=transaction_agent_chatkit,
        payment_agent=payment_agent_chatkit
    )
   