import logging

from agent_framework import Agent, BaseChatClient, MCPStreamableHTTPTool

from app.common.internal_identity import mcp_header_provider
from app.helpers.user_profile_provider import UserProfileProvider


logger = logging.getLogger(__name__)

class TransactionHistoryAgent :
    instructions = """
    you are a personal financial advisor who help the user with their recurrent bill payments. To search about the payments history you need to know the payee name.
    By default you should search the last 10 account transactions ordered by date.    
    If the user want to search last account transactions for a specific payee, extract it from the request and use it as filter.
    
    Use markdown list or table to display the transaction information.
    Always use the logged user details to retrieve account info.
    """
    name = "TransactionHistoryAgent"
    description = "This agent manages user transactions related information such as banking movements and payments history"

    def __init__(self, azure_chat_client: BaseChatClient,
                 account_mcp_server_url: str,
                 transaction_mcp_server_url: str,
                 internal_identity_secret: str,
                  ):
        self.azure_chat_client = azure_chat_client
        self.account_mcp_server_url = account_mcp_server_url
        self.transaction_mcp_server_url = transaction_mcp_server_url
        self.internal_identity_secret = internal_identity_secret
      


    def build_af_agent(self) -> Agent:
    
      logger.info("Building request scoped transaction agent run ")
      
      logger.info("Initializing Account MCP, Transaction MCP server tools for TransactionHistoryAgent ")
      
      account_mcp_server = MCPStreamableHTTPTool(
          name="Account MCP server client",
          url=self.account_mcp_server_url,
          header_provider=mcp_header_provider(self.internal_identity_secret),
       )
      
      transaction_mcp_server = MCPStreamableHTTPTool(
          name="Transaction MCP server client",
          url=self.transaction_mcp_server_url,
          header_provider=mcp_header_provider(self.internal_identity_secret),
     )  
      
      return Agent(
          client=self.azure_chat_client,
          instructions=TransactionHistoryAgent.instructions.strip(),
          name=TransactionHistoryAgent.name,
          require_per_service_call_history_persistence=True,
          tools=[account_mcp_server, transaction_mcp_server],
          context_providers=[UserProfileProvider()]
      )