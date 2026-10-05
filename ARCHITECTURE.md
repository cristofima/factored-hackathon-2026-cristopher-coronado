# Architecture of the Banking Assistant Prototype

## Bird's Eye View

This is an AI-first banking customer-service prototype built for the Factored AI &
Data Hackathon 2026, extending the public
`Azure-Samples/agent-openai-python-banking-assistant` sample. It implements one
coherent workflow: Account/Transaction inquiries through a conversational agent, with
a single persisted support-case layer on top for transaction disputes.

The system combines a React frontend, a database-free Responses BFF that owns the
browser trust boundary, dedicated Identity for credentials and lifecycle, a Responses
agent (Microsoft Agent Framework `HandoffBuilder`, served through Foundry Responses)
for triage and conversation, and two FastMCP business services (Account, Transaction)
for financial data and business rules. PostgreSQL is the only operational data store;
Terraform defines the five-site App Service stack separately from the hosted agent.

The one deliberate architectural split to internalize before changing anything: the
BFF is scoped to identity and chat-proxying only. The browser calls Account and
Transaction directly over REST for every financial read (accounts, cards,
transactions, support cases); it never goes through the BFF for those. The BFF is
only in the loop for allowlisted login/profile/admin facades and the customer
Responses chat stream. Dedicated Identity owns credentials, profiles and lifecycle;
the BFF has no database connection.

## Code Map

### `app/frontend/banking-web/`

React + Vite + shadcn-ui. `src/api/` holds `authClient.ts` (BFF login/profile),
`financialClient.ts` (Account/Transaction direct reads), `disputeClient.ts`
(customer support cases), and `operatorDisputeClient.ts` (operator queue/detail and
versioned exclusive claim). Transaction clients call its absolute `VITE_*_API_URL`
origin directly with the application JWT, never through a dev-server proxy.
`src/pages/` holds one page per screen, including `SupportCases.tsx`,
`SupportCaseDetail.tsx` and role-guarded `OperatorCases.tsx`. `src/locales/` holds the static `en`/`es`/`pt` UI catalogs
consumed by `UiLocaleProvider`. `src/components/DisputePreviewConsent.tsx` shares
proposal context, accept/decline and bounded recovery between `ReportDisputeDialog`
and the chat `DisputePreview` widget. Legacy `DisputeConsent` handles only persisted
pending-case decisions; generic MCP permission controls remain separate.

### `app/responses-bff/bff/`

`main.py` wires the FastAPI app. `auth.py` fronts allowlisted Identity
operations and checks current active identity/version without caching. `responses.py`
proxies the customer-only Responses SSE stream to the local or Foundry-hosted agent.
`internal_identity.py` signs the verified identity envelope the agent re-verifies.
`credentials.py` obtains the Azure access token server-side for hosted mode. This
package does not import or query Account/Transaction/PostgreSQL financial tables;
that boundary was deliberately removed in the 2026-10-01 direct-API migration (see
`docs/adr/0005-frontend-calls-account-and-transaction-directly.md`).

### `app/business-api/identity/`

Dedicated FastAPI identity service: Argon2 login, HS256 issuance, customer/operator/
admin profiles, fixed-role operator management, active/inactive lifecycle, identity
version and atomic audit. Access JWTs default to 60 minutes; refresh sessions and
renewal modals are deferred. An explicit seed service bootstraps an admin from external
credentials; it never runs at startup. Protected introspection uses a separate
`AUTH_INTERNAL_SECRET`. Staff have no `customer_id` and cannot use financial REST
or customer chat. See [ADR 0006](docs/adr/0006-dedicated-auth-users-and-staff-identities.md).

### `app/agent/app/`

`main_responses_host.py` is the Responses entry point, local and hosted.
`agents/azure_chat/hosted_workflow.py` builds the triage + Account + Transaction
specialist agents as one `HandoffBuilder` workflow using `FoundryChatClient` and MCP
tools; it constructs a request-local workflow per call to avoid shared mutable
executor state. `helpers/user_profile_provider.py` injects authenticated locale and
localized human-label instructions. Transaction intake requires preview and explicit
consent before mutation; REST-accepted cases continue via `getSupportCase` readback.
`tools/` holds the MCP client wiring. `routers/` exposes the local
`/responses` endpoint CRUDmakers's BFF proxies to.

### `app/business-api/account/` and `app/business-api/transaction/`

Both follow the same four-file shape: `mcp_tools.py` (agent-only tool definitions,
authenticated via `internal_identity.py`'s 60-second bearer), `routers.py` /
`dispute_routers.py` (browser-facing REST, authenticated via `jwt_identity.py`'s
`get_jwt_customer_id`, same HS256 secret/issuer/audience as the BFF),
`services.py` (business logic and the customer-ownership authorization check), and
`models.py` (Pydantic/SQLModel types). Transaction additionally owns
`dispute_service.py` (customer consent, review classification against the dataset's
`fraud_score`, and separately authorized resolution) and `dispute_routers.py`
(`/api/support-cases`). Read-only preview precedes explicit consent; signed-token
acceptance atomically creates the case, consent and routing in `IN_REVIEW`, while
preview/decline create no case/events. Acceptance lasts ten minutes; read-only recovery
lasts 24 hours from issuance and never treats null as proof of a failed write.
Legacy `WAITING_USER_APPROVAL` cases retain their decision path. See the
[consent contract](app/business-api/transaction/README.md#customer-dispute-proposal-and-consent).
A score never resolves a case. The approved operator ownership contract is documented in
[ADR 0008](docs/adr/0008-operator-ownership-without-service-agent-catalog.md): exclusive
claim records responsibility, not adjudication or financial authority by itself.
[ADR 0009](docs/adr/0009-operator-verdicts-with-recorded-financial-effects.md)
approves the separate assigned-operator verdict and recorded-compensation boundary:
valid cases stay pending until actual financial effects succeed; debit compensation
uses owned savings/checking allocation, not an inferred card-account relationship.
Card protection is separately audited and does not imply processor enforcement.
Both services enable `CORSMiddleware` via `CORS_ALLOWED_ORIGINS`.

### `app/business-api/shared/banking_shared/`

The shared SQLModel package: one class defines both the Postgres table and the
API/tool schema for types like `Account`, `Card`, `Transaction`, `SupportCase`,
consumed by Account, Transaction, and the data pipeline so there is exactly one
schema definition, never three.

### `app/business-api/data/`

The CSV-to-PostgreSQL ingestion pipeline. `scripts/run_pipeline.py` is the only
normal entry point (EDA, scope approval, loading, verification, in that order).
`scripts/evaluate_fraud_threshold.py` is the offline baseline evaluation for the
dispute triage threshold. Alembic migrations live alongside the SQLModel schema.

### `infra/`

Terraform only (no Bicep in this repo). One Linux App Service plan, five App
Services (`identity`, `account`, `transaction`, Responses BFF, `web`), Log Analytics,
Application Insights, and a Foundry account/project. Identity has a dedicated resource
and database-secret reference; consumers use its computed HTTPS hostname. Managed
identities receive secret-scoped access; BFF has no database setting/grant. Root azd
uses service-tag discovery, while standalone Identity CD uses its name output.
Provisioning, remote DB grants, migrations and coordinated rollout remain separate
acceptance gates; Terraform declarations are not deployed-isolation evidence.

### `app/agent/azure.yaml` vs root `azure.yaml`

Two independent `azd` project roots: the root manifest provisions the App Service
stack via Terraform; `app/agent/azure.yaml` provisions the hosted Foundry agent
separately. Commands against the agent stack need `--cwd app/agent`.

## Cross-Cutting Concerns

- **Dual authentication, never conflated.** `jwt_identity.py` (browser-issued
  application JWT, shared secret with the BFF) authenticates every REST endpoint a
  human calls directly. `internal_identity.py` (60-second HMAC bearer, minted fresh
  per MCP call) authenticates every tool call the agent makes. Neither substitutes
  for the other.
- **Authorization lives in `services.py`, not in prompts.** Every method that reads
  or acts on an `accountId`/`productId`/case id re-derives the owner from the
  verified identity and checks it against the resource before doing anything;
  no caller-supplied `customer_id` is ever trusted.
- **Tool schemas and agent instructions stay English-only.** Only the final
  response text is locale-driven, from the authenticated user's stored `locale`
  (`es`/`pt`/`en`, `en` fallback), injected once per request by a context provider,
  never inferred from the current message's language. Human-facing status labels
  are translated without changing canonical transport codes. Frontend catalogs map
  Card to Card/Tarjeta/Cartão; Spanish generated/display terminology uses
  `reclamo`/`reclamos` with masculine grammar. Customer reasons and original audit
  text remain verbatim; frontend catalogs never translate agent Markdown.
- **Dispute legitimacy is never an LLM decision.** `dispute_service.py`'s triage
  is a deterministic routing check against the dataset's precomputed `fraud_score`;
  missing scores stay in review without estimation. The agent's only job is intake
  (identify and confirm the transaction), read-only case consultation and routing.
  `operator_service.py` separately enforces available/assigned lists, owner-only
  detail and atomic exclusive claims. Real ownership references `operators.user_id`;
  retired simulated assignments remain archives, not authentication or verdicts.
- **Testing is per-service, not repo-wide.** `pytest` (`pytest-asyncio`,
  `asyncio_mode = "auto"`) per Python service under its own `tests/`; `vitest` for
  the frontend. There is no single top-level test runner.
- **`uv` is the only supported Python tool runner** inside each service directory;
  commands run as `uv run`/`uv sync` from that service's own root, not from the
  repo root.

## Architectural Invariants

- The BFF never queries Account, Transaction, or PostgreSQL financial tables
  directly. If a future change adds that back, it reopens a closed migration
  (`docs/adr/0005-...md`) and needs the same explicit sign-off that closed it.
- `plan/` is gitignored and local-only. Nothing under it is ever staged, committed,
  or pushed, regardless of how much planning content accumulates there.
- No second conversational specialist agent exists beside Account and Transaction.
  The transaction-dispute support case is a tracking/workflow layer over those two
  existing MCP tool surfaces, not a third `HandoffBuilder` participant.
- `mcp_tools.py` and `routers.py`/`dispute_routers.py` are thin: they validate
  input, call one `services.py` method, and shape the response. They never contain
  an authorization check or a business rule themselves.
- The conversational model never invents an eligibility, fraud, or dispute-outcome
  rule; those are deterministic policy/threshold checks, with the model only
  explaining results already computed by code.
