from fastmcp import FastMCP
from fastmcp.server.dependencies import CurrentHeaders
import logging
from dispute_service import support_case_service_singleton as dispute_service
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


@mcp.tool(
    name="reportTransactionDispute",
    description=(
        "Open a transaction-dispute support case for a transaction the customer does not "
        "recognize or disputes. Use this after confirming the specific transaction with the "
        "customer. This only opens the case and requests the customer's approval; it never "
        "decides whether the dispute is legitimate. The case is persisted; approval "
        "does not block a card, issue credit or a refund, post a transaction, or change balances."
    ),
)
def report_transaction_dispute(
    transaction_id: str,
    reason: str,
    headers: dict[str, str] = CurrentHeaders(),
):
    return dispute_service.open_transaction_dispute(
        transaction_id,
        get_customer_id(headers),
        reason,
    )


@mcp.tool(
    name="respondToDisputeApproval",
    description=(
        "Record the customer's approval or decline for a dispute case awaiting approval. "
        "Only call this after the customer has explicitly confirmed or declined. Approval "
        "continues persisted case processing, not a human investigation or verdict. Legacy "
        "outcome codes do not establish credit, refund, balance, or card-protection effects."
    ),
)
def respond_to_dispute_approval(
    case_id: str,
    approved: bool,
    headers: dict[str, str] = CurrentHeaders(),
):
    return dispute_service.respond_to_approval(case_id, get_customer_id(headers), approved)


@mcp.tool(name="listSupportCases", description="List the customer's transaction-dispute support cases")
def list_support_cases(
    headers: dict[str, str] = CurrentHeaders(),
):
    return dispute_service.list_cases(get_customer_id(headers))


@mcp.tool(name="getSupportCase", description="Get a single transaction-dispute support case by ID")
def get_support_case(
    case_id: str,
    headers: dict[str, str] = CurrentHeaders(),
):
    return dispute_service.get_case(case_id, get_customer_id(headers))


@mcp.tool(
    name="getSupportCaseTimeline",
    description=(
        "Get the event timeline for a persisted transaction-dispute support case. Prefer "
        "displayMessage for user-facing text; message preserves original audit text. "
        "Historical outcome words do not prove financial effects or a human verdict."
    ),
)
def get_support_case_timeline(
    case_id: str,
    headers: dict[str, str] = CurrentHeaders(),
):
    return dispute_service.get_case_timeline(case_id, get_customer_id(headers))


