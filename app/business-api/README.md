# Banking Assistant Business API - Python FastMCP Services

A collection of Python-based FastMCP servers used by the Banking Assistant. Account and Transaction read PostgreSQL-backed dataset rows through the shared SQLModel package and expose inquiry tools through the Model Context Protocol (MCP).

## 🏗️ Architecture

This business API layer contains **specialized MCP servers** for different banking domains:

- **Account Service**: Active workflow dependency for account details, payment methods, and beneficiaries
- **Transaction Service**: Active workflow dependency for transaction history and search operations

Each service runs as an independent FastMCP server exposing banking tools through HTTP endpoints that the copilot agents can consume.

## App Service Deployment

Identity is a separate HTTP identity service, not an MCP specialist. It owns
persisted users and JWT issuance; see the [Identity guide](./identity/README.md).
Identity, Account and Transaction deploy independently through the root
[azd manifest](../../azure.yaml) to Terraform-provisioned App Services.

| Service     | GitHub `Development` Variable | Terraform output / azd variable |
| ----------- | ----------------------------- | ------------------------------- |
| Identity    | `AZURE_IDENTITY_APP_NAME`     | `AZURE_IDENTITY_APP_NAME`       |
| Account     | `AZURE_ACCOUNT_APP_NAME`      | `AZURE_ACCOUNT_APP_NAME`        |
| Transaction | `AZURE_TRANSACTION_APP_NAME`  | `AZURE_TRANSACTION_APP_NAME`    |

Set GitHub Variables manually from the physical name outputs. Shared CD exports
those values under the same `_APP_NAME` azd names; `resourceName` and preflight target the
same app, with no tag-discovery fallback. Identity reuses the shared `database-url`
Key Vault secret; the BFF remains database-free. Packaging does not migrate the
database or create users, and resolved references do not prove runtime readiness.
See the [workflow guide](../../.github/workflows/README.md#required-github-environment-variables)
and [infrastructure guide](../../infra/README.md) for configuration and rollout.

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- Git

> [!WARNING]
> Each service has its own `.venv`. Select the interpreter in the service directory you are running (for example, `transaction/.venv/Scripts/python.exe` on Windows).

> [!NOTE]
> Account and Transaction require `DATABASE_URL`, `INTERNAL_IDENTITY_SECRET` (MCP),
> and `JWT_SECRET_KEY` (browser REST) to start without a `503`. `CORS_ALLOWED_ORIGINS`
> defaults to `http://localhost:5170` if unset. Configure each service's own `.env`
> using its `.env.example`; see [Configuration](#configuration) below.

> [!NOTE]
> Docker deployment paths were removed along with the per-service Dockerfiles. Run the servers directly with Python or package them using the shared App Service workflow.

## 🔧 Service Setup

Each service follows the same setup pattern. Navigate to the specific service directory and follow below steps. Examples are shown for account service, make sure to adjust paths and environment variables for the transaction service:

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

## 🛠️ Available Banking Tools

Each service exposes two parallel surfaces that never share an auth mechanism:

- **MCP tools** (`mcp_tools.py`), mounted at `/mcp`, called only by the Responses agent.
  They authenticate with `internal_identity.py`'s short-lived HMAC bearer, minted
  fresh per request from the BFF-verified identity the agent receives.
- **REST endpoints** (`routers.py`, `dispute_routers.py`), mounted at `/api`, called
  directly by the browser. They authenticate with `jwt_identity.py`'s
  `get_jwt_customer_id`, which validates the application JWT Identity issues through
  the BFF at login (HS256, `JWT_SECRET_KEY`/`JWT_ISSUER`/`JWT_AUDIENCE`) and verifies
  active customer status and the current identity version through protected Identity
  introspection. CORS is enabled via
  `CORS_ALLOWED_ORIGINS` (defaults to `http://localhost:5170`).

### Account Service (Port 8070)

MCP tools:

- **`getAccountsByUserName`** - Get all accounts for a specific user
- **`getAccountDetails`** - Get account details and available payment methods
- **`getRegisteredBeneficiary`** - Get registered beneficiaries for an account (unavailable for persisted products)
- **`getCreditCards`** - Get the list of credit cards bound to an account
- **`getCardDetails`** - Get the details of a single credit card

REST endpoints (`/api` prefix):

- **`GET /accounts`** - List every bank account owned by the authenticated customer
- **`GET /cards`** - List every card owned by the authenticated customer
- **`GET /accounts/{product_number}/cards`**, **`GET /cards/{product_number}`**,
  **`POST /cards/{card_id}/recharge`**, **`POST /cards/{card_id}/pay`** - existing
  single-resource operations (recharge/pay are unavailable for persisted products)

### Transaction Service (Port 8071)

MCP tools:

- **`getTransactionsByRecipientName`** - Search transactions by recipient name
- **`getLastTransactions`** - Get recent transaction history for an account
- **`getCardTransactions`** - Get credit and debit card transactions
- **`reportTransactionDispute`**, **`respondToDisputeApproval`**, **`listSupportCases`**,
  **`getSupportCase`**, **`getSupportCaseTimeline`** - transaction-dispute support-case
  workflow (intake/triage only; the agent never decides legitimacy)

REST endpoints (`/api/transactions` prefix):

- **`GET /{product_number}`** - Last 5 transactions, or filtered by `payment_type`/`transaction_type`/`card_product_number`
- **`GET /{product_number}/history`** - Owned bank-account history with inclusive `start_date`/`end_date`, `limit`, `offset`
- **`GET /products/{product_id}/history`** - Owned credit/debit-card history with the same date filters and pagination; the opaque product ID is not a card number

New disputes accept card transactions only; historical account cases remain readable.
No debit-card/account relationship is inferred from shared customer ownership.

Support-case REST endpoints at `/api/support-cases` (same JWT auth) additionally expose
`POST /{case_id}/approval`, `POST /{case_id}/recommendation/dismiss` (records the
customer's explicit opt-out of the single post-resolution recommendation), and
`POST /{case_id}/resolve` (ownership-checked and customer-authenticated, never
exposed as an MCP tool; it is not an operator-only endpoint).

Approval transitions every classification to `IN_REVIEW`. Low scores retain the
`fast_track` routing classification and emit `REVIEW_REQUIRED`, but no longer close
the case automatically or generate a resolution outcome/recommendation. High and
missing scores retain their escalation classifications. All classifications assign
a reviewer-catalog entry when available; absent catalog entries leave the case
unassigned and in review. Assignment is not operator takeover or human adjudication.

Resolution requires a separate explicit operation on an owned `IN_REVIEW` case.
Operator queues, takeover, adjudication, and automatic review timeouts are not
implemented. Historical resolved records remain unchanged. Case resolution does
not post credits, change balances, or block cards. The 365-day intake window is
unchanged and remains independent of fraud-score triage.

### Port Configuration

Services use different ports based on the `PROFILE` environment variable:

| Service     | Development Port | Production Port |
| ----------- | ---------------- | --------------- |
| Account     | 8070             | 8080            |
| Transaction | 8071             | 8080            |

## ⚙️ Configuration

| Variable                                | Used by              | Purpose / default                                                         |
| --------------------------------------- | -------------------- | ------------------------------------------------------------------------- |
| `DATABASE_URL`                          | Account, Transaction | Shared PostgreSQL connection (via `banking-shared`).                      |
| `INTERNAL_IDENTITY_SECRET`              | Account, Transaction | HMAC secret verifying the agent's short-lived MCP bearer.                 |
| `JWT_SECRET_KEY`                        | Account, Transaction | Must match the BFF's signing key; verifies the browser's application JWT. |
| `JWT_ISSUER` / `JWT_AUDIENCE`           | Account, Transaction | Default `home-banking-api` / `home-banking-web`, matching the BFF.        |
| `CORS_ALLOWED_ORIGINS`                  | Account, Transaction | Comma-separated browser origins; defaults to `http://localhost:5170`.     |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Account, Transaction | Optional Azure Monitor trace export.                                      |

### Distributed Tracing

FastAPI instrumentation surrounds each service's REST routes and mounted `/mcp/`
application. It extracts W3C `traceparent` and `tracestate` from agent requests, or
starts a new trace for browser REST calls without context. Service resource names
are `banking-assistant-account` and `banking-assistant-transaction`. Export is optional;
propagation and server spans remain available without an Application Insights connection.
The setup does not enable body or authentication-header capture.

In-memory tests verify MCP context reception. Correlation across the deployed
Foundry gateway remains unverified. The App Service startup command must also trust
the controlled Azure proxy's forwarded scheme so `/mcp` redirects remain HTTPS;
the Terraform startup-command correction requires provisioning, not just zip deployment.

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
# MCP Server URLs (from app/agent/.env)
ACCOUNT_MCP_URL=http://localhost:8070
TRANSACTION_MCP_URL=http://localhost:8071
```

The copilot's active specialist agents use these tools to:

- **Account Agent**: Query account details and payment methods
- **Transaction Agent**: Search and retrieve transaction history

Account and Transaction MCP endpoints require a short-lived bearer created by the
Responses agent from BFF-verified identity. Their `services.py` methods enforce
`customer_id` ownership through persisted product relationships and transaction-row
filters before returning customer-owned resources. Keep those checks in the service layer;
tool descriptions and agent instructions are not authorization boundaries.

The browser calls Account and Transaction REST endpoints directly, authenticated with
the application JWT issued by the [Responses BFF](../responses-bff/README.md) at
login. The BFF itself only handles identity (`/auth/login`, `/auth/me`) and fronts the
Responses agent; it does not read account, card, or transaction data from PostgreSQL.
Browser application JWTs are not substitutes for the internal MCP bearer, and the two
auth dependencies (`jwt_identity.get_jwt_customer_id` for REST, `internal_identity.get_customer_id`
for MCP) are never interchangeable.

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
