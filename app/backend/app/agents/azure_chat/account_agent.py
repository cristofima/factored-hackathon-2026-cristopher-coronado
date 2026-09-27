from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework import Agent, MCPStreamableHTTPTool
from app.helpers.user_profile_provider import UserProfileProvider

import logging


logger = logging.getLogger(__name__)

class AccountAgent :
    instructions = """
    you are a personal financial advisor who help the user to retrieve information about their bank accounts.
    Always use markdown to format your response.
    Always use the logged user details to retrieve account info.
    """
    name = "AccountAgent"
    description = "This agent manages user accounts related information such as balance, credit cards."

    def __init__(self, azure_chat_client: OpenAIChatCompletionClient, account_mcp_server_url: str):
        self.azure_chat_client = azure_chat_client
        self.account_mcp_server_url = account_mcp_server_url



    async def build_af_agent(self)-> Agent:
    
      logger.info("Initializing Account Agent connection for account api ")
      
      logger.info("Initializing Account MCP server tools for AccountAgent ")
      account_mcp_server = MCPStreamableHTTPTool(
                name="Account MCP server client",
                url=self.account_mcp_server_url)
      
      await account_mcp_server.connect()
      return Agent(
                client=self.azure_chat_client,
                instructions=AccountAgent.instructions.strip(),
                name=AccountAgent.name,
                require_per_service_call_history_persistence=True,
                tools=[account_mcp_server],
                context_providers=[UserProfileProvider()]
            )
        
