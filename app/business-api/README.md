# Banking Assistant Business API - Python FastMCP Services

A collection of Python-based FastMCP servers used by the Banking Assistant. Account and Transaction read PostgreSQL-backed dataset rows through the shared SQLModel package and expose inquiry tools through the Model Context Protocol (MCP). Payment remains an inherited compatibility service outside the active workflow.

## 🏗️ Architecture

This business API layer contains **specialized MCP servers** for different banking domains:

- **Account Service**: Active workflow dependency for account details, payment methods, and beneficiaries
- **Transaction Service**: Active workflow dependency for transaction history and search operations
- **Payment Service**: Inherited compatibility service, not connected to the active agent workflow

Each service runs as an independent FastMCP server exposing banking tools through HTTP endpoints that the copilot agents can consume.

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- Git

> [!WARNING]
> Each service has its own `.venv`. Select the interpreter in the service directory you are running (for example, `transaction/.venv/Scripts/python.exe` on Windows).

> [!NOTE]
> Docker deployment paths were removed along with the per-service Dockerfiles. Run the servers directly with Python or package them using the shared App Service workflow.

## 🔧 Service Setup

Each service follows the same setup pattern. Navigate to the specific service directory and follow below steps. Examples are shown for account service, make sure to adjust paths and environment variables for payment and transaction services:

### 1. Account Service Setup

```powershell
cd app/business-api/account
```

#### Install dependencies using uv and run

```powershell
# Install uv if you don't have it
pip install uv

# Create a virtual environment
uv venv

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Install all dependencies
uv sync

# Run the Account MCP Server (FastAPI + MCP)

$env:PROFILE="dev"
python main.py
```

The Account service will be available at: **http://localhost:8070**

---

### 2. Transaction Service Setup

```powershell
cd app/business-api/transaction
```

#### Install dependencies and run

```powershell
# Create virtual environment and install dependencies
uv venv
.\.venv\Scripts\Activate.ps1
uv sync

# Run the Transaction MCP Server (FastAPI + MCP)
$env:PROFILE="dev"
python main.py
```

The Transaction service will be available at: **http://localhost:8071**

---

### 2. Payment Service Setup

```powershell
cd app/business-api/payment
```

#### Install dependencies and run

```powershell
# Create virtual environment and install dependencies
uv venv
.\.venv\Scripts\Activate.ps1
uv sync

# Run the Payment MCP Server
$env:PROFILE="dev"
$env:TRANSACTIONS_API_SERVER_URL="http://localhost:8071"
python main.py
```

The Payment service will be available at: **http://localhost:8072**

## 🛠️ Available Banking Tools

### Account Service (Port 8070)

Exposes the following MCP tools:

- **`getAccountsByUserName`** - Get all accounts for a specific user
- **`getAccountDetails`** - Get account details and available payment methods
- **`getPaymentMethodDetails`** - Get payment method details with available balance
- **`getRegisteredBeneficiary`** - Get registered beneficiaries for an account

### Payment Service (Port 8072)

Exposes the following MCP tools:

- **`processPayment`** - Submit and process payment requests with full transaction details

### Transaction Service (Port 8071)

Exposes the following MCP tools:

- **`getTransactionsByRecipientName`** - Search transactions by recipient name
- **`getLastTransactions`** - Get recent transaction history for an account

Additionally provides REST API endpoints at `/api/transactions` for direct HTTP access.

### Port Configuration

Services use different ports based on the `PROFILE` environment variable:

| Service     | Development Port | Production Port |
| ----------- | ---------------- | --------------- |
| Account     | 8070             | 8080            |
| Transaction | 8071             | 8080            |
| Payment     | 8072             | 8080            |

## 📁 Service Structure

Each service follows a consistent structure:

```
service-name/
├── main.py                 # FastMCP server entry point
├── mcp_tools.py           # MCP tool definitions (@mcp.tool decorators)
├── services.py            # Business logic and data access
├── models.py              # Pydantic data models
├── logging_config.py      # Logging configuration
├── pyproject.toml         # Project dependencies
├── uv.lock               # Lock file for reproducible builds
```

## 🔌 Integration with Copilot

The Banking Assistant Copilot connects to these services via MCP URLs configured in its environment:

```env
# MCP Server URLs (from app/backend/.env.dev)
ACCOUNT_MCP_URL=http://localhost:8070
TRANSACTION_MCP_URL=http://localhost:8071
```

The copilot's active specialist agents use these tools to:

- **Account Agent**: Query account details and payment methods
- **Transaction Agent**: Search and retrieve transaction history

The Payment service remains in this directory but is not connected to the active agent workflow.

Account and Transaction MCP endpoints require a short-lived bearer created by the
Responses agent from BFF-verified identity. Their `services.py` methods enforce
`customer_id` ownership through persisted product relationships and transaction-row
filters before returning customer-owned resources. Keep those checks in the service layer;
tool descriptions and agent instructions are not authorization boundaries.

The [Responses BFF](../responses-bff/README.md) separately reads persisted users,
customer names, and owned savings/checking products for browser login and the Account
page. Browser application JWTs are not substitutes for the internal MCP bearer.

## 🐛 Development & Debugging

Launch the services individually or press `F5` with `DEV - Full Stack Ordered` to start Account, Transaction, the local Responses agent, the BFF, and Vite; see the [root local-development guide](../../README.md#local-development-vs-code). Set breakpoints in any service and the running process will honor them.

## Local inquiry verification

On 2026-09-30, user-supplied local browser evidence through the BFF confirmed an
owned-account answer and a foreign-account denial against the persisted-data path.
The foreign request called `getAccountDetails` with `product_number`; its tool
result was `ACCESS_DENIED`, followed by a visible assistant denial and a completed
Responses stream without foreign financial data. This is a tool-level denial,
not an HTTP 403 for the successful SSE transport.

Public lookup parameters use product numbers rather than internal product keys.
Bank numbers are displayed in full; card numbers are masked. Full Transaction chat,
missing/empty, multi-turn, and deployed authorization matrices remain pending.

Account and Transaction use loaded hackathon dataset rows, not live bank integrations.
The [data module guide](data/README.md) covers ingestion and demo identity seeding.
Production banking integration and deployment security controls remain outside this prototype.
