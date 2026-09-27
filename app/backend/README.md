# Banking Assistant Copilot Backend

A FastAPI-based multi-agent orchestration service that powers the banking assistant frontend. This microservice uses Azure OpenAI and the Agent Framework to provide intelligent banking support through specialized agents.

## 🏗️ Architecture

This backend implements a **supervisor agent pattern** where:

- **Supervisor Agent**: Routes user requests to specialized domain agents
- **Account Agent**: Handles account balance, payment methods, and beneficiaries
- **Transaction Agent**: Manages banking movements and payment history
- **Payment Agent**: Processes payment requests using bill details supplied by the user

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher and uv
- Access to an Azure AI Services resource with an Azure OpenAI chat deployment
- Azure CLI signed in with an identity assigned `Cognitive Services OpenAI User` on that resource for local development

### Backend Setup

#### 1. Navigate to the backend directory

```powershell
cd app/backend
```

#### 2. Install dependencies using uv

```powershell
uv sync --extra dev
```

#### 3. Configure environment variables

Set `PROFILE=dev` before starting the backend. Its settings load `.env` and then `.env.dev`; use the latter for your local Azure OpenAI connection details. The endpoint must be the resource root URL, not a `/chat/completions` or `/openai/v1` route:

```env
# Azure OpenAI Settings
AZURE_OPENAI_ENDPOINT=https://your-resource.services.ai.azure.com/
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME=your-chat-deployment

# Azure Blob Storage for ChatKit attachments
AZURE_STORAGE_ACCOUNT=your-storage-account
AZURE_STORAGE_CONTAINER=content

# Local MCP servers
ACCOUNT_MCP_URL=http://localhost:8070
TRANSACTION_MCP_URL=http://localhost:8071
PAYMENT_MCP_URL=http://localhost:8072
```

Sign in using `az login` in the same Azure CLI context used to start the backend. The VS Code Azure sign-in is independent of this identity. The backend obtains a Cognitive Services bearer token via `AzureCliCredential`; it does not use the signed-in VS Code account or an OpenAI API key in this profile.

#### 4. Run the development server

**Option A: Using uvicorn directly**

```powershell
$env:PROFILE="dev"
uv run uvicorn app.main_chatkit_server:app --port 8080
```

The ChatKit endpoint is `http://localhost:8080/chatkit`; the root path returns 404 by design. Start the local MCP services before submitting a chat request. The root [README](../../README.md#local-development-vs-code) also describes the VS Code `F5` launch, which opens the frontend on port 5170.

### Verified local inquiry

On 2026-09-26, a browser `threads.create` request returned a transaction-history answer via `TransactionHistoryAgent`. Azure OpenAI chat completions returned HTTP 200, and `getAccountsByUserName` and `getTransactionsByRecipientName` both succeeded against local MCP services. An HTTP 200 on `/chatkit` alone only confirms that the SSE connection started; verify the assistant's final answer and tool events as well. This does not verify payment submission, end-user authorization, or hosted deployment.

---

## 🎨 Frontend Setup

### 1. Navigate to the frontend directory

```powershell
cd app/frontend/banking-web
```

### 2. Install dependencies

```powershell
npm install
```

### 3. Start the development server

```powershell
npm run dev
```

Open the URL printed by Vite (normally `http://localhost:5170/`).

---

## 📁 Project Structure

```
app/backend/
├── app/
│   ├── main_chatkit_server.py  # FastAPI application entry point
│   ├── routers/chatkit/        # ChatKit and attachment endpoints
│   ├── agents/
│   │   ├── azure_chat/
│   │   │   ├── handoff_orchestrator.py  # Main routing agent
│   │   │   ├── account_agent.py         # Account management
│   │   │   ├── transaction_agent.py     # Transaction history
│   │   │   └── payment_agent.py         # Payment processing
│   ├── config/
│   │   └── container_azure_chat.py      # DI container
│   └── helpers/              # Azure service helpers
├── pyproject.toml              # Project dependencies
└── .env.dev                    # Optional local environment configuration
```

---

## 🌊 Streaming Support

The backend streams ChatKit SSE events for progress, agent handoffs, tool calls, and assistant messages through `/chatkit`.

---
