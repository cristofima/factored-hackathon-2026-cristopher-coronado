from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework import Agent, MCPStreamableHTTPTool
from app.helpers.user_profile_provider import UserProfileProvider
from app.helpers.no_history_provider import NoHistoryProvider

import logging


logger = logging.getLogger(__name__)

class PaymentAgent :
    instructions = """
    you are a personal financial advisor who helps the user with their recurrent bill payments. The user may start a payment by providing bill details or checking transaction history for a specific payee.
        For the bill payment you need to know the: bill id or invoice number, payee name, the total amount.
        If you don't have enough information to pay the bill ask the user to provide the missing information.
        If the user uploads an invoice image, explain that image extraction is unavailable and ask for the bill details in text. Do not infer details from the attachment.
        Always check if the bill has been already paid based on payment history before asking to execute the bill payment.
        Ask for the payment method to use based on the available methods on the user account.
        if the user wants to pay using bank transfer, check if the payee is in account registered beneficiaries list. If not ask the user to provide the payee bank code.
        Check if the payment method selected by the user has enough funds to pay the bill. Don't use the account balance to evaluate the funds.
        Before submitting the payment to the system ask the user confirmation providing the payment details.
        Include in the payment description the invoice id or bill id as following: payment for invoice 1527248.
        Extract a category for the payment based on the payee name (for example utilities, rent, mortgage, insurance, subscriptions, phone, internet, etc..)
        Payment status is 'paid' when submitting a payment with CreditCard. Status is 'pending' when submitting a payment with BankTransfer.
        When submitting payment always use the available functions to retrieve accountId, paymentMethodId.
        If the payment succeeds provide the user with the payment confirmation. If not provide the user with the error message.
        Use markdown list or table to display bill details, payments, account or transaction details.
        Always use the below logged user details to retrieve account info:
       {user_mail}
        Current timestamp:
       {current_date_time}
        Don't try to guess accountId,paymentMethodId from the conversation.When submitting payment always use functions to retrieve accountId, paymentMethodId.
        
        """
    name = "PaymentAgent"
    description = "This agent manages user payments related information such as submitting payment requests and bill payments."

    def __init__(self, azure_chat_client: OpenAIChatCompletionClient,
                  account_mcp_server_url: str,
                  transaction_mcp_server_url: str,
                  payment_mcp_server_url: str):
        self.azure_chat_client = azure_chat_client
        self.account_mcp_server_url = account_mcp_server_url
        self.transaction_mcp_server_url = transaction_mcp_server_url
        self.payment_mcp_server_url = payment_mcp_server_url
        

    async def build_af_agent(self) -> Agent:
    
      logger.info("Building request scoped Payment agent run ")
      
      logger.info("Initializing Account MCP, Transaction MCP, Payment MCP server tools for PaymentAgent") 
      
      account_mcp_server = MCPStreamableHTTPTool(
        name="Account MCP server client",
        url=self.account_mcp_server_url
      )
      transaction_mcp_server = MCPStreamableHTTPTool(
        name="Transaction MCP server client",
        url=self.transaction_mcp_server_url
      )
      payment_mcp_server = MCPStreamableHTTPTool(
        name="Payment MCP server client",
        url=self.payment_mcp_server_url,
        approval_mode = { "always_require_approval": ["processPayment"] }
      )

      await account_mcp_server.connect()
      await transaction_mcp_server.connect()
      await payment_mcp_server.connect()
      full_instruction = PaymentAgent.instructions.format(user_mail=UserProfileProvider._get_logged_user_email(), 
                                                          current_date_time=UserProfileProvider._get_current_timestamp())
      return Agent(
      client=self.azure_chat_client,
      instructions=full_instruction.strip(),
      name=PaymentAgent.name,
      require_per_service_call_history_persistence=True,
      tools=[account_mcp_server,
              transaction_mcp_server, 
              payment_mcp_server],
      # NoHistoryProvider prevents the framework from auto-injecting an
      # InMemoryHistoryProvider.  Inside a HandoffBuilder workflow the
      # executor already tracks the full conversation, so the auto-injected
      # provider would duplicate messages on every turn, eventually causing
      # OpenAI 400 errors due to mismatched tool_calls / tool results.
      context_providers=[NoHistoryProvider()])
            
        