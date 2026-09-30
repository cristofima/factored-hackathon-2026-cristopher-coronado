from fastmcp import FastMCP
from fastmcp.server.dependencies import CurrentHeaders
import logging
from internal_identity import get_customer_id
from services import transaction_service_singleton as service

logger = logging.getLogger(__name__)
mcp = FastMCP("Transaction MCP Server")


@mcp.tool(name="getTransactionsByRecipientName", description="Get transactions by recipient name")
def get_transactions_by_recipient_name(
    product_number: str,
    recipientName: str,
    headers: dict[str, str] = CurrentHeaders(),
):
    return service.get_transactions_by_recipient_name(
        product_number,
        recipientName,
        get_customer_id(headers),
    )

@mcp.tool(name="getCardTransactions", description="Get credit and debit card transactions")
def get_card_transactions(
    product_number: str,
    card_product_number: str,
    headers: dict[str, str] = CurrentHeaders(),
):
    return service.get_transactions_by_type(
        account_id=product_number,
        customer_id=get_customer_id(headers),
        card_id=card_product_number,
    )


@mcp.tool(name="getLastTransactions", description="Get the last transactions for an account")
def get_last_transactions(
    product_number: str,
    headers: dict[str, str] = CurrentHeaders(),
):
    return service.get_transactions(product_number, get_customer_id(headers))


