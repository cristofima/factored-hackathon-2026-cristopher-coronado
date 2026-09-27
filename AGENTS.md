## Technical Stack

### Backend Technologies

#### Core Framework

- **Python 3.11+**: Primary programming language
- **FastAPI 0.141.1**: Modern web framework for building APIs with automatic OpenAPI documentation
- **Uvicorn 0.37.0**: Lightning-fast ASGI server implementation

#### AI & Agent Framework

- **Microsoft Agent Framework (MAF)**:
  - `agent-framework-core 1.19.0`: Core agent orchestration capabilities
  - `agent-framework-openai 1.14.4`: Azure OpenAI Chat Completions client used by the kept `azure_chat/` agents
  - `agent-framework-orchestrations 1.2.0`: `HandoffBuilder` and other orchestration patterns
  - `agent-framework-chatkit 1.0.0b260910`: ChatKit protocol implementation for agent-to-chat communication (still pre-release upstream)
- **OpenAI ChatKit 1.6.5**: Client-side chat protocol implementation
- **Azure OpenAI (GPT-4.1)**: Large language model for agent intelligence

#### Azure Services Integration

- **Azure Identity 1.25.3**: Authentication and authorization with Azure services
- **Azure Storage Blob 12.30.3**: Document and file storage
- **Azure Document Intelligence 1.0.2**: OCR and invoice/receipt data extraction
- **Azure Monitor OpenTelemetry**: Observability and telemetry

#### Additional Backend Tools

- **dependency-injector 4.48.1**: Dependency injection container for clean architecture
- **pytest 9.1.1** / **pytest-asyncio 1.4.0**: Testing framework with async support

### Frontend Technologies

#### Banking Web (Primary Frontend)

- **React 18.2+**: Modern UI library
- **TypeScript**: Type-safe JavaScript development
- **Vite**: Next-generation frontend build tool
- **shadcn/ui**: Re-usable component library built on:
  - **Radix UI**: Accessible component primitives
  - **Tailwind CSS**: Utility-first CSS framework
  - **class-variance-authority**: Type-safe component variants
- **TanStack Query 5.56.2**: Powerful data synchronization
- **Lucide React 0.462.0**: Beautiful icon library
- **React Hook Form & Zod**: Form handling and validation

### Infrastructure & DevOps

#### Cloud Platform

- **Azure Container Apps**: Serverless container hosting platform
- **Azure AI Foundry**: AI model deployment and management
- **Azure Cognitive Services**: AI capabilities (Document Intelligence)
- **Azure Monitor & Application Insights**: Observability and monitoring

#### Infrastructure as Code

- **Bicep**: Azure's domain-specific language for declarative infrastructure
- **Azure Developer CLI (azd)**: Automated deployment and provisioning
- **Docker**: Containerization with multi-stage builds

#### Build Tools

- **uv**: Fast Python package installer and resolver
- **npm/pnpm**: Package management (banking-web)

### Communication Protocols

- **Model Context Protocol (MCP)**: Exposing business APIs as agent tools via [fastmcp](https://gofastmcp.com/)
- **OpenAI ChatKit Protocol**: Extended implementation supporting:
  - Server-Sent Events (SSE) streaming
  - Client-managed widgets
  - Multi-agent workflows
  - Human-in-the-loop (HITL) patterns

---

## Repository Structure

### Root Level Files

```
📄 azure.yaml              # Azure Developer CLI configuration defining all services
📄 README.md               # Project overview and getting started guide
📄 CHANGELOG.md            # Version history and release notes
📄 CONTRIBUTING.md         # Contribution guidelines
📄 LICENSE.md              # MIT License
📄 SECURITY.md             # Security policy and reporting guidelines
📄 CODEOWNERS              # GitHub code owners configuration
```

### `/app` - Application Source Code

Main application directory containing all backend, frontend, and business API components.

#### `/app/backend` - Agent Backend Service

The core multi-agent orchestration service that exposes chat API endpoints.

```
📁 app/backend/
├── 📄 pyproject.toml                    # Python project dependencies and metadata
├── 📄 README.md                         # Backend-specific documentation
├── 📄 applicationinsights.json          # Application Insights configuration
│
├── 📁 app/                              # Main application package
│   ├── 📄 main_chatkit_server.py        # Entry point for ChatKit server mode
│   ├── 📄 logging-default.yaml          # Logging configuration
│   │
│   ├── 📁 agents/                       # Agent implementations
│   │   └── 📁 azure_chat/               # Azure OpenAI Chat-based agents (the only kept implementation)
│   │       │                            #   - Uses Azure OpenAI Chat client based agents
│   │       │                            #   - Agents are optimized for ChatKit protocol implementations
│   │       │                            #   - Files: account_agent.py, payment_agent.py,
│   │       │                            #     transaction_agent.py, handoff_orchestrator.py
│   │
│   ├── 📁 common/                       # Shared utilities and base classes
│   │
│   ├── 📁 config/                       # Configuration management
│   │   ├── 📄 azure_credential.py       # Azure authentication credential provider
│   │   │                                #   - Provides environment-aware credential selection
│   │   │                                #   - Dev: Azure CLI credentials for local development
│   │   │                                #   - Prod: Managed Identity for Azure-hosted environments
│   │   │                                #   - Supports both sync and async credential instances
│   │   ├── 📄 settings.py               # Application settings and environment variable management
│   │   │                                #   - Pydantic-based settings with validation
│   │   │                                #   - Loads from environment variables and .env files
│   │   │                                #   - Azure service configurations (OpenAI, Storage, Document Intelligence)
│   │   │                                #   - MCP server URLs for business API integration
│   │   │                                #   - Profile-based configuration (dev/prod)
│   │   ├── 📄 logging.py                # Logging configuration and OpenTelemetry setup
│   │   │                                #   - Profile-based logging configuration (logging-{profile}.yaml)
│   │   │                                #   - OpenTelemetry integration for distributed tracing
│   │   │                                #   - Application Insights log export
│   │   │                                #   - Structured logging with custom formatters
│   │   ├── 📄 container_azure_chat.py   # DI container for Azure OpenAI Chat agents
│   │   │                                #   - Dependency injection using dependency-injector
│   │   │                                #   - Configures Azure OpenAI Chat client instances
│   │   │                                #   - Wires agents with Azure services (Blob Storage, Document Intelligence)
│   │   │                                #   - Supports both simple handoff and ChatKit protocol agents
│   │
│   ├── 📁 helpers/                      # Azure service proxies and utilities
│   │   │                                #   - Simplifies interaction with Azure services (blob, other Azure AI services)
│   │
│   ├── 📁 models/                       # Data models and schemas
│   ├── 📁 routers/                      # FastAPI route handlers
│   └── 📁 tools/                        # Agent tools and plugins
│       └── 📄 invoice_scanner_plugin.py # Document Intelligence integration
│
└── 📁 tests/                            # Unit and integration tests
    ├── 📄 conftest.py                   # Shared test fixtures
    ├── 📄 test_chatkit_new_thread.py    # New thread SSE event flow
    ├── 📄 test_chatkit_multi_turn.py    # Multi-turn conversation context
    ├── 📄 test_chatkit_payment.py       # HITL payment approval flow
    ├── 📄 test_chatkit_payment_with_image.py # Payment flow with invoice image upload
    └── 📄 test_chatkit_thread_list.py   # Thread listing isolated by user
```

#### `/app/business-api` - Business Domain Services

Microservices exposing business logic as REST APIs and MCP tools.

```
📁 business-api/
├── 📄 README.md                         # Business API documentation
├── 📁 account/                          # Account management service
├── 📁 payment/                          # Payment processing service
└── 📁 transaction/                      # Transaction history service
```

**Key Responsibilities:**

- Domain-specific business logic
- RESTful API endpoints
- MCP tool exposure for agent consumption
- Mock data generation for demo scenarios
- Integration with backend data stores

#### `/app/frontend` - User Interface Applications

The kept React/Vite/shadcn-ui frontend.

##### `/app/frontend/banking-web` - Primary Modern UI

```
📁 banking-web/
├── 📄 package.json                      # Node.js dependencies
├── 📄 bun.lockb                         # Bun lock file
├── 📄 vite.config.ts                    # Vite build configuration
├── 📄 tsconfig.json                     # TypeScript configuration
├── 📄 tailwind.config.ts                # Tailwind CSS configuration
├── 📄 components.json                   # shadcn/ui components config
├── 📄 index.html                        # HTML entry point
│
├── 📁 src/                              # Source code
│   ├── 📁 components/                   # React components
│   ├── 📁 hooks/                        # Custom React hooks
│   ├── 📁 lib/                          # Utility libraries
│   ├── 📁 pages/                        # Page components
│   └── 📁 styles/                       # CSS/styling files
│
└── 📁 public/                           # Static assets
```

**Features:**

- Modern banking UI with shadcn/ui components
- Reusable chat widget component
- Image upload support for invoices/receipts
- Responsive design with Tailwind CSS
- Type-safe with TypeScript

### `/data` - Sample Data & Assets

Contains sample invoices, receipts, and banking data for demonstration purposes.

```
📁 data/
├── 📁 invoices/                         # Sample invoice PDFs/images
├── 📁 receipts/                         # Sample receipt images
└── 📁 transactions/                     # Mock transaction data
```

### `/docs` - Documentation

Comprehensive technical and user documentation.

```
📁 docs/
├── 📄 technical-architecture.md         # Detailed architecture documentation
├── 📄 chat-server-protocol.md           # ChatKit protocol implementation details
├── 📄 deployment-guide.md               # Step-by-step deployment instructions
├── 📄 client-managed-widgets.md         # Client-side widget documentation
├── 📄 server-managed-widgets.md         # Server-side widget documentation
├── 📄 faq.md                            # Frequently asked questions
├── 📄 troubleshooting.md                # Common issues and solutions
│
├── 📁 assets/                           # Documentation images and diagrams

```

### `/infra` - Infrastructure as Code

Bicep templates for Azure resource provisioning.

```
📁 infra/
├── 📄 main.bicep                        # Main infrastructure orchestration
├── 📄 main.parameters.json              # Environment-specific parameters
│
├── 📁 app/                              # Application-specific resources
│   ├── 📄 account.bicep                 # Account service infrastructure
│   ├── 📄 backend.bicep                 # Backend service infrastructure
│   ├── 📄 payment.bicep                 # Payment service infrastructure
│   ├── 📄 transaction.bicep             # Transaction service infrastructure
│   └── 📄 web.bicep                     # Web frontend infrastructure
│
└── 📁 shared/                           # Shared infrastructure components
    ├── 📄 abbreviations.json            # Azure resource naming conventions
    ├── 📄 backend-dashboard.bicep       # Application Insights dashboard
    │
    ├── 📁 ai/                           # AI service infrastructure
    │   ├── 📄 cognitiveservices.bicep   # Cognitive Services setup
    │   ├── 📄 foundry.bicep             # AI Foundry hub/project setup
    │   └── 📄 foundry-model-deployment.bicep # Model deployment configs
    │
    ├── 📁 host/                         # Container hosting infrastructure
    │   ├── 📄 container-app.bicep       # Individual container app definition
    │   ├── 📄 container-apps.bicep      # Multiple container apps
    │   ├── 📄 container-app-upsert.bicep # Container app update logic
    │   ├── 📄 container-apps-environment.bicep # Container Apps environment
    │   └── 📄 container-registry.bicep  # Azure Container Registry
    │
    ├── 📁 monitor/                      # Monitoring and observability
    │   └── 📄 applicationinsights-dashboard.bicep # Monitoring dashboards
    │
    ├── 📁 security/                     # Security and identity
    │   └── [Key Vault, Managed Identity configs]
    │
    └── 📁 storage/                      # Storage resources
        └── [Blob Storage, File Share configs]
```

**Key Infrastructure Components:**

- **Container Apps Environment**: Serverless container hosting
- **Azure AI Foundry**: GPT-4.1 model deployment
- **Cognitive Services**: Document Intelligence for OCR
- **Application Insights**: Distributed tracing and monitoring
- **Container Registry**: Docker image storage
- **Managed Identity**: Secure service-to-service authentication

---

## Deployment Model

### Deployment Status

The [application manifest](azure.yaml) and [App Service CI workflow](.github/workflows/app-ci.yaml) target ZIP deployment for the Python services. The hosted-agent project now uses [app/backend/azure.yaml](app/backend/azure.yaml) as a separate azd root for Foundry operations. Use `azd` from the repository root for the App Service stack and use `azd --cwd app/backend ...` for the hosted-agent stack. The existing [Bicep infrastructure](infra/main.bicep) still defines Container Apps and ACR, and static frontend serving is not fully reconciled with ZIP deployment.
The frontend App Service naming convention in the root Terraform stack is `app-banking-web-<env>` (for example, `app-banking-web-development`).

### Local Development

The root [.vscode/launch.json](.vscode/launch.json) and [.vscode/tasks.json](.vscode/tasks.json) own the `DEV - Full Stack Ordered` launch. Pressing `F5` starts the three MCP services (8070-8072), ChatKit (8080), and Vite (5170), then opens `http://localhost:5170/`. Keep port 5170 available when using this launch configuration.

### Observability

- **Application Insights**: Request tracing, dependency tracking
- **OpenTelemetry**: Distributed tracing across agents and services

---

## Integration Tests

Integration tests validate the full ChatKit SSE event flow end-to-end, hitting the `/chatkit` endpoint with mock MCP servers and a real Azure OpenAI backend.

### Prerequisites

- **Azure OpenAI credentials** configured in `app/backend/.env.dev` (`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`)
- **Python dependencies** installed (including dev extras)

### Setup

```bash
cd app/backend
uv sync --extra dev
```

### Running Tests

```bash
# Run all tests
uv run python -m pytest tests/ -v -s

# Run a specific test module
uv run python -m pytest tests/test_chatkit_new_thread.py -v -s
uv run python -m pytest tests/test_chatkit_multi_turn.py -v -s
uv run python -m pytest tests/test_chatkit_payment.py -v -s
```

### Test Architecture

- **Mock MCP servers**: In-process FastMCP servers (account, transaction, payment) start on random free ports with sample data. They replicate the real business API tool signatures.
- **Configuration**: Tests set `PROFILE=dev` to load `.env.dev` for Azure OpenAI config, then override `ACCOUNT_MCP_URL`, `TRANSACTION_MCP_URL`, and `PAYMENT_MCP_URL` to point to the mock servers.
- **Telemetry**: `APPLICATIONINSIGHTS_CONNECTION_STRING` is cleared so `configure_azure_monitor` is skipped during tests.
- **ASGI transport**: Tests use `httpx.AsyncClient` with `ASGITransport` and `asgi-lifespan` to call the FastAPI app in-process (no real HTTP server needed for the backend).

### Test Flows

| Test Class                         | Description                                                                                                                                                                                                                                                                                                                              |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TestChatkitNewThreadFlow`         | Creates a new thread, sends a question about Contoso payments, and validates the full SSE event sequence: `thread.created` → `user_message` → `progress_update` → `task` events → streaming `text_delta` → final `assistant_message`.                                                                                                    |
| `TestChatkitMultiTurnConversation` | Two-turn conversation in the same thread. First asks about Contoso, then follows up with "what about ACME" to verify the agent preserves conversation context across turns.                                                                                                                                                              |
| `TestChatkitPaymentFlow`           | Multi-turn payment with human-in-the-loop approval. User requests a bill payment → selects card → agent emits `tool_approval_request` widget → user approves via `threads.custom_action` → agent confirms payment. The test adapts to LLM variability (the agent may compress or expand the number of turns before requesting approval). |

---
