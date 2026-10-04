import logging

from agent_framework import Agent, BaseChatClient, MCPStreamableHTTPTool
from mcp import ClientSession

from app.common.internal_identity import mcp_header_provider
from app.helpers.tool_error_middleware import OwnershipErrorMiddleware
from app.helpers.user_profile_provider import UserProfileProvider


logger = logging.getLogger(__name__)

class TransactionHistoryAgent :
    instructions = """
    you are a personal financial advisor who help the user with their recurrent bill payments. To search about the payments history you need to know the payee name.
    By default you should search the last 10 account transactions ordered by date.    
    If the user want to search last account transactions for a specific payee, extract it from the request and use it as filter.
    
    Use markdown list or table to display the transaction information.
    Always use the logged user details to retrieve account info.
    Resource lookup tools accept product_number (and card_product_number for card lookups),
    never database product ids. Use the full number supplied by the user. If only a masked
    number is available, ask for the full number; never reconstruct it or submit masked digits.
    Bank account numbers may be shown in full. Credit and debit card numbers must remain masked,
    including card numbers supplied by the user. Preserve tool-returned card masking.
    If a tool denies ownership, stop and state that the account is unavailable without
    listing other accounts or disclosing financial data.

    Movement inquiries cover bank accounts, Debit Card, and Credit Card products separately.
    Never infer a card-to-account relationship from shared customer ownership or combine
    their histories. New transaction disputes are supported only for Debit Card and Credit
    Card transactions, not bank account transactions. Verify the product type before
    reporting a dispute; if it is unknown, establish it with the lookup tools first.
    Existing support cases remain available for status and timeline inquiries regardless
    of product type.

    Transaction-dispute support cases: if the customer does not recognize a transaction or
    wants to dispute one, first identify the specific transaction using the transaction
    lookup tools and confirm it with the customer (amount, merchant, and date) before
    acting. Then call reportTransactionDispute with that transaction_id and the customer's
    stated reason. This only opens the case and requests the customer's approval; you must
    never decide, imply, or state whether the dispute is legitimate or will succeed. After
    opening a case, explicitly explain that confirmation continues the persisted dispute
    workflow; no card block, refund, provisional credit, posting, or balance change is
    implemented. Call respondToDisputeApproval only after the customer clearly approves or
    declines. A catalog assignment alone does not establish a human investigation or
    legitimacy verdict. Operator adjudication is not yet implemented. Legacy resolution
    outcome codes do not prove executed effects. For timeline display, prefer displayMessage
    over the original stored message and distinguish recorded case processing from
    investigation, verdict, and financial effects. Use listSupportCases, getSupportCase, and
    getSupportCaseTimeline to answer status questions about existing cases. If opening a
    case fails (for example an inactive card, a non-approved transaction, an existing case
    on that transaction, or a transaction outside the dispute window), relay the tool's
    reason to the customer in plain language without inventing a cause.
    """
    name = "TransactionHistoryAgent"
    description = "This agent manages user transactions related information such as banking movements and payments history"

    def __init__(self, azure_chat_client: BaseChatClient,
                 account_mcp_server_url: str,
                 transaction_mcp_server_url: str,
                 internal_identity_secret: str,
                 *,
                 account_mcp_session: ClientSession | None = None,
                 transaction_mcp_session: ClientSession | None = None,
                  ) -> None:
        self.azure_chat_client = azure_chat_client
        self.account_mcp_server_url = account_mcp_server_url
        self.transaction_mcp_server_url = transaction_mcp_server_url
        self.internal_identity_secret = internal_identity_secret
        self.account_mcp_session = account_mcp_session
        self.transaction_mcp_session = transaction_mcp_session
      


    def build_af_agent(self) -> Agent:
    
      logger.info("Building request scoped transaction agent run ")
      
      logger.info("Initializing Account MCP, Transaction MCP server tools for TransactionHistoryAgent ")
      
      account_mcp_server = MCPStreamableHTTPTool(
          name="Account MCP server client",
          url=self.account_mcp_server_url,
          session=self.account_mcp_session,
          header_provider=(mcp_header_provider(self.internal_identity_secret)
                           if self.account_mcp_session is None else None),
       )
      
      transaction_mcp_server = MCPStreamableHTTPTool(
          name="Transaction MCP server client",
          url=self.transaction_mcp_server_url,
          session=self.transaction_mcp_session,
          header_provider=(mcp_header_provider(self.internal_identity_secret)
                           if self.transaction_mcp_session is None else None),
     )  
      
      return Agent(
          client=self.azure_chat_client,
          instructions=TransactionHistoryAgent.instructions.strip(),
          name=TransactionHistoryAgent.name,
          require_per_service_call_history_persistence=True,
          tools=[account_mcp_server, transaction_mcp_server],
          middleware=[OwnershipErrorMiddleware()],
          context_providers=[UserProfileProvider(self.internal_identity_secret)]
      )