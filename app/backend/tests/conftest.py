"""Shared fixtures and helpers for chatkit integration tests.

Provides mock MCP servers (account, transaction, payment), SSE parsing
utilities, and the chatkit ASGI app + async client fixtures.

Requirements:
- Azure OpenAI credentials (AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_CHAT_DEPLOYMENT_NAME)
- MCP servers are started in-process as mock servers with sample data
"""

import asyncio
import json
import logging
import socket
import threading
from typing import List

import pytest
import uvicorn
from fastapi import FastAPI
from fastmcp import FastMCP
from httpx import ASGITransport, AsyncClient

# Suppress noisy MCP client teardown errors (cancel scope / async generator cleanup)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)


# ---------------------------------------------------------------------------
# Mock MCP servers with sample data matching business-api services
# ---------------------------------------------------------------------------

def _create_account_mcp_app() -> FastAPI:
    """Create a mock Account MCP server with sample data."""
    mcp = FastMCP("Account MCP Server")

    accounts_by_username = {
        "bob.user@contoso.com": [
            {
                "id": "1010",
                "userName": "bob.user@contoso.com",
                "accountHolderFullName": "Bob User",
                "currency": "EUR",
                "activationDate": "2022-01-01",
                "balance": "10000",
                "paymentMethods": [
                    {"id": "345678", "type": "BankTransfer", "activationDate": "2022-01-01", "expirationDate": "9999-01-01"},
                    {"id": "55555", "type": "Visa", "name": "Primary Platinum", "activationDate": "2024-03-01", "expirationDate": "2027-03-01"},
                    {"id": "66666", "type": "Visa", "name": "Secondary Gold", "activationDate": "2025-11-01", "expirationDate": "2028-11-01"},
                ],
            }
        ],
        "alice.user@contoso.com": [
            {
                "id": "1000",
                "userName": "alice.user@contoso.com",
                "accountHolderFullName": "Alice User",
                "currency": "USD",
                "activationDate": "2022-01-01",
                "balance": "5000",
                "paymentMethods": [
                    {"id": "12345", "type": "Visa", "activationDate": "2022-01-01", "expirationDate": "2025-01-01"},
                    {"id": "23456", "type": "BankTransfer", "activationDate": "2022-01-01", "expirationDate": "9999-01-01"},
                ],
            }
        ],
    }

    account_details = {
        "1010": {
            "id": "1010",
            "userName": "bob.user@contoso.com",
            "accountHolderFullName": "Bob User",
            "currency": "EUR",
            "activationDate": "2022-01-01",
            "balance": "10000",
            "paymentMethods": [
                {"id": "345678", "type": "BankTransfer", "activationDate": "2022-01-01", "expirationDate": "9999-01-01"},
                {"id": "55555", "type": "Visa", "name": "Primary Platinum", "activationDate": "2024-03-01", "expirationDate": "2027-03-01"},
                {"id": "66666", "type": "Visa", "name": "Secondary Gold", "activationDate": "2025-11-01", "expirationDate": "2028-11-01"},
            ],
        },
        "1000": {
            "id": "1000",
            "userName": "alice.user@contoso.com",
            "accountHolderFullName": "Alice User",
            "currency": "USD",
            "activationDate": "2022-01-01",
            "balance": "5000",
            "paymentMethods": [
                {"id": "12345", "type": "Visa", "activationDate": "2022-01-01", "expirationDate": "2025-01-01"},
                {"id": "23456", "type": "BankTransfer", "activationDate": "2022-01-01", "expirationDate": "9999-01-01"},
            ],
        },
    }

    @mcp.tool(name="getAccountsByUserName", description="Get the list of all accounts for a specific user")
    def get_accounts_by_user_name(userName: str) -> list:
        return accounts_by_username.get(userName, [])

    @mcp.tool(name="getAccountDetails", description="Get account details and available payment methods")
    def get_account_details(accountId: str) -> dict | None:
        return account_details.get(accountId)

    @mcp.tool(name="getRegisteredBeneficiary", description="Get list of registered beneficiaries for a specific account")
    def get_registered_beneficiary(accountId: str) -> list:
        return [
            {"id": "1", "fullName": "Mike ThePlumber", "bankCode": "123456789", "bankName": "Intesa Sanpaolo"},
            {"id": "2", "fullName": "Jane TheElectrician", "bankCode": "987654321", "bankName": "UBS"},
        ]

    @mcp.tool(name="getCreditCards", description="Get the list of credit cards bound to an account")
    def get_credit_cards(accountId: str) -> list:
        cards_by_account = {
            "1010": [
                {"id": "55555", "type": "credit", "circuit": "visa", "name": "Primary Platinum", "activationDate": "2024-03-01", "expirationDate": "2027-03-01", "balance": 900.5, "number": "5111222233335555", "limit": 3000.0, "status": "active"},
                {"id": "66666", "type": "recharge", "circuit": "visa", "name": "Virtual Gold", "activationDate": "2025-11-01", "expirationDate": "2028-11-01", "balance": 640.25, "number": "5211222233336666", "limit": 2500.0, "status": "active"},
                {"id": "77777", "type": "credit", "circuit": "amex", "name": "Executive Black", "activationDate": "2024-02-01", "expirationDate": "2029-02-01", "balance": 0, "number": "5311222233337777", "limit": 20000.0, "status": "blocked"},
            ],
        }
        return cards_by_account.get(accountId, [])

    @mcp.tool(name="getCardDetails", description="Get the details of a single credit card")
    def get_card_details(cardId: str) -> dict | None:
        cards = {
            "55555": {"id": "55555", "type": "credit", "circuit": "visa", "name": "Primary Platinum", "balance": 900.5},
            "66666": {"id": "66666", "type": "recharge", "circuit": "visa", "name": "Virtual Gold", "balance": 640.25},
        }
        return cards.get(cardId)

    mcp_app = mcp.http_app(path="/")
    app = FastAPI(title="Mock Account MCP Server", lifespan=mcp_app.lifespan)
    app.mount("/mcp", mcp_app)
    return app


def _create_transaction_mcp_app() -> FastAPI:
    """Create a mock Transaction MCP server with sample data."""
    mcp = FastMCP("Transaction MCP Server")

    all_transactions = {
        "1010": [
            {"id": "232334", "description": "Payment for office supply services", "type": "payment", "flowType": "outcome", "recipientName": "Contoso", "recipientBankReference": "0002", "accountId": "1010", "paymentType": "CreditCard", "cardId": "55555", "amount": 215.00, "timestamp": "2025-03-02T12:00:00Z", "category": "Supply services", "status": "paid"},
            {"id": "3321432", "description": "Business Lunch with customer", "type": "payment", "flowType": "outcome", "recipientName": "Duff", "accountId": "1010", "paymentType": "CreditCard", "cardId": "66666", "amount": 134.10, "timestamp": "2025-10-03T12:00:00Z", "category": "Meals", "status": "paid"},
            {"id": "884995", "description": "Office Air conditioners. Invoice 355TRA1423FFSSS", "type": "payment", "flowType": "outcome", "recipientName": "Contoso Services", "recipientBankReference": "0003", "accountId": "1010", "paymentType": "DirectDebit", "amount": 300.00, "timestamp": "2025-10-03T12:00:00Z", "category": "Services", "status": "paid"},
            {"id": "3946373", "description": "Metro and Bus subscription 2023-AB56", "type": "payment", "flowType": "outcome", "recipientName": "Speedy Subways", "recipientBankReference": "0005", "accountId": "1010", "paymentType": "CreditCard", "cardId": "66666", "amount": 410.00, "timestamp": "2025-04-05T12:00:00Z", "category": "Retail", "status": "paid"},
            {"id": "2004764", "description": "Medical eyes checkup payment. Ref: MZ23-5567", "type": "payment", "flowType": "outcome", "recipientName": "Contoso Health", "recipientBankReference": "0001", "accountId": "1010", "paymentType": "CreditCard", "cardId": "66666", "amount": 230.00, "timestamp": "2025-11-01T12:00:00Z", "category": "Health", "status": "paid"},
            {"id": "49950598", "description": "Payment of the bill 682222", "type": "payment", "flowType": "outcome", "recipientName": "Contoso Services", "recipientBankReference": "0002", "accountId": "1010", "paymentType": "CreditCard", "cardId": "55555", "amount": 200.00, "timestamp": "2025-11-02T12:00:00Z", "category": "Rent", "status": "paid"},
            {"id": "488624", "description": "Monthly Salary - StartUp.com", "type": "deposit", "flowType": "income", "accountId": "1010", "paymentType": "Transfer", "amount": 3000.00, "timestamp": "2025-10-03T12:00:00Z", "category": "Payroll"},
            {"id": "3004853", "description": "Stocks vesting accreditation. www.traderepublic.com - FY25Q3", "type": "deposit", "flowType": "income", "accountId": "1010", "paymentType": "Transfer", "amount": 400.00, "timestamp": "2025-8-04T12:00:00Z", "category": "Investment"},
            {"id": "5001001", "description": "Home power bill 334398", "type": "payment", "flowType": "outcome", "recipientName": "ACME", "recipientBankReference": "0010", "accountId": "1010", "paymentType": "BankTransfer", "amount": 160.40, "timestamp": "2026-04-07T12:00:00Z", "category": "Utilities", "status": "pending"},
            {"id": "5001002", "description": "Office cleaning services March", "type": "payment", "flowType": "outcome", "recipientName": "ACME Services", "recipientBankReference": "0011", "accountId": "1010", "paymentType": "CreditCard", "cardId": "55555", "amount": 95.00, "timestamp": "2026-03-15T12:00:00Z", "category": "Services", "status": "paid"},
        ],
    }

    last_transactions = {
        "1010": [
            {"id": "11", "description": "Home power bill 334398", "type": "payment", "flowType": "outcome", "recipientName": "ACME", "recipientBankReference": "0001", "accountId": "1010", "paymentType": "BankTransfer", "amount": 160.40, "timestamp": "2026-04-07T12:00:00Z", "category": "Utilities", "status": "pending"},
            {"id": "22", "description": "Payment for office supply services", "type": "payment", "flowType": "outcome", "recipientName": "Contoso Services", "recipientBankReference": "0002", "accountId": "1010", "paymentType": "CreditCard", "cardId": "card-8421", "amount": 215.00, "timestamp": "2025-03-02T12:00:00Z", "category": "Supply services", "status": "paid"},
            {"id": "33", "description": "Business Lunch with customer", "type": "payment", "flowType": "outcome", "recipientName": "Duff", "accountId": "1010", "paymentType": "CreditCard", "cardId": "card-8421", "amount": 134.10, "timestamp": "2025-10-03T12:00:00Z", "category": "Meals", "status": "paid"},
            {"id": "43", "description": "card withdrawal at atm 00987", "type": "withdrawal", "flowType": "outcome", "accountId": "1010", "paymentType": "DirectDebit", "cardId": "card-3311", "amount": 150.00, "timestamp": "2025-8-04T12:00:00Z", "category": "Insurance"},
            {"id": "53", "description": "Refund for invoice 19dee", "type": "deposit", "flowType": "income", "recipientName": "oscorp", "recipientBankReference": "0005", "accountId": "1010", "paymentType": "BankTransfer", "amount": 522.00, "timestamp": "2025-4-05T12:00:00Z", "category": "Refunds", "cardId": "card-0098"},
        ],
    }

    @mcp.tool(name="getTransactionsByRecipientName", description="Get transactions by recipient name")
    def get_transactions_by_recipient_name(accountId: str, recipientName: str) -> list:
        transactions = all_transactions.get(accountId, [])
        name_lower = recipientName.lower() if recipientName else ""
        filtered = [t for t in transactions if t.get("recipientName") and name_lower in t["recipientName"].lower()]
        return sorted(filtered, key=lambda t: t["timestamp"], reverse=True)

    @mcp.tool(name="getCardTransactions", description="Get credit and debit card transactions")
    def get_card_transactions(accountId: str, cardId: str) -> list:
        transactions = all_transactions.get(accountId, [])
        return [t for t in transactions if t.get("cardId") == cardId]

    @mcp.tool(name="getLastTransactions", description="Get the last transactions for an account")
    def get_last_transactions(accountId: str) -> list:
        return sorted(
            last_transactions.get(accountId, []),
            key=lambda t: t["timestamp"],
            reverse=True,
        )

    mcp_app = mcp.http_app(path="/")
    app = FastAPI(title="Mock Transaction MCP Server", lifespan=mcp_app.lifespan)
    app.mount("/mcp", mcp_app)
    return app


def _create_payment_mcp_app() -> FastAPI:
    """Create a mock Payment MCP server with a single processPayment tool."""
    mcp = FastMCP("Payment MCP Server")

    @mcp.tool(name="processPayment", description="Submit a payment request")
    def process_payment(
        account_id: str,
        amount: float,
        description: str,
        timestamp: str,
        recipient_name: str | None = None,
        recipient_bank_code: str | None = None,
        payment_type: str | None = None,
        card_id: str | None = None,
        status: str | None = None,
        category: str | None = None,
    ) -> dict:
        if not account_id or not account_id.isdigit():
            return {"status": "error", "message": "Invalid accountId"}
        if payment_type == "CreditCard" and not card_id:
            return {"status": "error", "message": "cardId is required for CreditCard payments"}
        return {"status": "ok"}

    mcp_app = mcp.http_app(path="/")
    app = FastAPI(title="Mock Payment MCP Server", lifespan=mcp_app.lifespan)
    app.mount("/mcp", mcp_app)
    return app


# ---------------------------------------------------------------------------
# Helper: start a uvicorn server in a background thread on a free port
# ---------------------------------------------------------------------------

def _find_free_port() -> int:
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _BackgroundServer:
    """Run a uvicorn ASGI server in a daemon thread."""

    def __init__(self, app: FastAPI, port: int):
        self.config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        self.server = uvicorn.Server(self.config)
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self.server.run, daemon=True)
        self._thread.start()
        # Wait until the server is accepting connections
        import time
        for _ in range(50):
            if self.server.started:
                break
            time.sleep(0.1)

    def stop(self) -> None:
        self.server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def parse_sse_events(raw_body: str) -> List[dict]:
    """Parse an SSE text body into a list of JSON event dicts.

    Each SSE frame looks like:
        data: {"type":"...", ...}\n\n

    Some frames may contain stream_options or other metadata.
    Lines that are not ``data:`` prefixed are ignored.
    """
    events: List[dict] = []
    for line in raw_body.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if payload:
                try:
                    events.append(json.loads(payload))
                except json.JSONDecodeError:
                    pass  # skip malformed lines
    return events


def get_events_by_type(events: List[dict], event_type: str) -> List[dict]:
    """Filter parsed SSE events by their ``type`` field."""
    return [e for e in events if e.get("type") == event_type]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def mock_mcp_ports():
    """Allocate free ports for the mock MCP servers."""
    return {
        "account": _find_free_port(),
        "transaction": _find_free_port(),
        "payment": _find_free_port(),
    }


@pytest.fixture(scope="session")
def mock_mcp_servers(mock_mcp_ports):
    """Start mock Account, Transaction, and Payment MCP servers for the whole test session."""
    account_app = _create_account_mcp_app()
    transaction_app = _create_transaction_mcp_app()
    payment_app = _create_payment_mcp_app()

    account_srv = _BackgroundServer(account_app, mock_mcp_ports["account"])
    transaction_srv = _BackgroundServer(transaction_app, mock_mcp_ports["transaction"])
    payment_srv = _BackgroundServer(payment_app, mock_mcp_ports["payment"])

    account_srv.start()
    transaction_srv.start()
    payment_srv.start()

    yield mock_mcp_ports

    account_srv.stop()
    transaction_srv.stop()
    payment_srv.stop()


@pytest.fixture(scope="session")
def chatkit_app(mock_mcp_servers):
    """Create the FastAPI application with MCP URLs pointing to mock servers.

    Settings and the DI container are patched **before** the app is created
    so that agents will connect to the in-process mock MCP servers.
    """
    import os

    # Load configuration from .env.dev via the PROFILE mechanism
    os.environ["PROFILE"] = "dev"

    account_port = mock_mcp_servers["account"]
    transaction_port = mock_mcp_servers["transaction"]
    payment_port = mock_mcp_servers["payment"]

    # Override MCP URLs to point to in-process mock servers
    os.environ["ACCOUNT_MCP_URL"] = f"http://127.0.0.1:{account_port}/mcp"
    os.environ["TRANSACTION_MCP_URL"] = f"http://127.0.0.1:{transaction_port}/mcp"
    os.environ["PAYMENT_MCP_URL"] = f"http://127.0.0.1:{payment_port}/mcp"
    # Disable Application Insights telemetry during tests
    os.environ["ENABLE_OTEL"] = "false"
    os.environ.pop("APPLICATIONINSIGHTS_CONNECTION_STRING", None)

    # Settings will load from .env.dev for Azure OpenAI config; verify it's present
    from app.config.settings import Settings
    test_settings = Settings()

    if not test_settings.AZURE_OPENAI_ENDPOINT:
        pytest.skip(
            "AZURE_OPENAI_ENDPOINT is not configured. "
            "Ensure .env.dev has AZURE_OPENAI_ENDPOINT set to run integration tests."
        )

    # Now import and create the app — settings will read .env.dev + overrides above
    from app.main_chatkit_server import create_app

    return create_app()


@pytest.fixture(scope="session")
async def client(chatkit_app):
    """Yield an httpx AsyncClient wired to the chatkit ASGI app."""
    from asgi_lifespan import LifespanManager

    async with LifespanManager(chatkit_app) as manager:
        transport = ASGITransport(app=manager.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
