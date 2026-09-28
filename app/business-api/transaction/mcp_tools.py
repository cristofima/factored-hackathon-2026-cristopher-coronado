from fastmcp import FastMCP
from fastmcp.server.dependencies import CurrentHeaders
import logging
from internal_identity import get_customer_id
from services import transaction_service_singleton as service

logger = logging.getLogger(__name__)
mcp = FastMCP("Transaction MCP Server")


@mcp.tool(name="getTransactionsByRecipientName", description="Get transactions by recipient name")
def get_transactions_by_recipient_name(
    accountId: str,
    recipientName: str,
    headers: dict[str, str] = CurrentHeaders(),
):
    logger.info("getTransactionsByRecipientName called with accountId=%s, recipientName=%s", accountId, recipientName)
    return service.get_transactions_by_recipient_name(
        accountId,
        recipientName,
        get_customer_id(headers),
    )

@mcp.tool(name="getCardTransactions", description="Get credit and debit card transactions")
def get_card_transactions(
    accountId: str,
    cardId: str,
    headers: dict[str, str] = CurrentHeaders(),
):
    logger.info("getCardTransactions called with accountId=%s, cardId=%s", accountId, cardId)
    return service.get_transactions_by_type(
        account_id=accountId,
        customer_id=get_customer_id(headers),
        card_id=cardId,
    )


@mcp.tool(name="getLastTransactions", description="Get the last transactions for an account")
def get_last_transactions(
    accountId: str,
    headers: dict[str, str] = CurrentHeaders(),
):
    logger.info("getLastTransactions called with accountId=%s", accountId)
    return service.get_transactions(accountId, get_customer_id(headers))


