---
page_type: sample
languages:
  - azdeveloper
  - python
  - typescript
  - html
products:
  - ai-services
  - azure
  - azure-openai
  - active-directory
  - azure-cognitive-search
  - azure-sdks
  - github
  - azure-monitor
  - azure-pipelines
urlFragment: agent-openai-python-banking-assistant
name: Multi Agents Banking Assistant with Python and Microsoft Agent Framework
description: A Python sample app using Foundry Responses for account and transaction inquiries
---

<!-- YAML front-matter schema: https://review.learn.microsoft.com/en-us/help/contribute/samples/process/onboarding?branch=main#supported-metadata-fields-for-readmemd -->
<!-- prettier-ignore -->
<div align="center">

![](./docs/assets/robot-agents-small.png)

</div>

# Multi Agent Banking Assistant

This hackathon prototype extends Microsoft's public [Azure-Samples/agent-openai-python-banking-assistant](https://github.com/Azure-Samples/agent-openai-python-banking-assistant) sample. The current workflow focuses on Account and Transaction inquiries through Foundry Responses.

### What changed from the upstream sample

The upstream sample is a proof-of-concept with no persistence layer: account,
transaction, and payment data are in-memory/dummy fixtures, there is no end-user
authentication at all (access is controlled only by an Azure RBAC role assignment
on a publicly reachable Container App), and its supervisor plus three domain
agents (account, transaction, payment with Document Intelligence invoice OCR) are
co-located on Azure Container Apps, talking to the browser over the OpenAI ChatKit
protocol, provisioned with Bicep, running `gpt-4.1`.

This fork replaces each of those with a different answer rather than extending them
as-is:

| Area           | Upstream sample                                                         | This fork                                                                                                       |
| -------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Data           | In-memory/dummy fixtures, no database                                   | Azure Database for PostgreSQL Flexible Server via a shared SQLModel package, with a real CSV ingestion pipeline |
| Users          | None; RBAC-gated Container App, no end-user auth                        | Dedicated Identity, Argon2 credentials, role/lifecycle-aware JWTs, DB-free Responses BFF                        |
| Agent hosting  | Supervisor + 3 agents co-located on Container Apps                      | Account/Transaction handoff workflow deployed as a separately hosted Foundry agent, with its own `azd` project  |
| Protocol       | OpenAI ChatKit (client-managed widgets)                                 | OpenAI Responses API, proxied through the BFF                                                                   |
| Infra          | Bicep, Container Apps                                                   | Terraform, App Service                                                                                          |
| Workflow scope | Account + Transaction + Payment (invoice OCR via Document Intelligence) | Account + Transaction only; Payment dropped entirely, never wired to the agent                                  |
| Added          | —                                                                       | Persisted transaction-dispute support case with a customer approval gate, and `es`/`pt`/`en` localization       |
| Model          | `gpt-4.1`                                                               | `gpt-4.1-mini`                                                                                                  |

See [ARCHITECTURE.md](./ARCHITECTURE.md) and [the ADRs](./docs/adr/README.md) for
why each of these changed.

For the 2026-10-05 submission, the target audience is retail banking customers who need fast support resolution and clear balance-movement explanations. Dataset profiling shows higher monthly activity in 2026 than 2025 for selected customers, but the core value proposition remains workflow clarity, approval control, and end-to-end case traceability rather than high-volume optimization alone. The demo scope includes one contextual product recommendation after case resolution, with strict guardrails (single recommendation, rationale shown, and opt-out support) to avoid spam-like behavior.

A banking support prototype for customers who need to identify an unfamiliar
transaction, submit a dispute with explicit approval, and understand the case's
progress. The agent gathers context and explains service outcomes; deterministic
business logic routes the case, and the AI never decides dispute legitimacy.

New intake first returns an owned, read-only transaction proposal. Explicit consent
then records case creation, consent and review routing atomically in `IN_REVIEW`;
decline creates no case or event. Existing pending cases retain their legacy approval
path. Signed proposals have bounded acceptance/recovery, and chat reads back cases
accepted through the manual action instead of recreating them. See the
[Transaction consent contract](app/business-api/transaction/README.md#customer-dispute-proposal-and-consent).

Consent and review do not themselves adjudicate, refund or protect a card. Separately
implemented assigned-operator verdicts record financial effects under
[ADR 0009](docs/adr/0009-operator-verdicts-with-recorded-financial-effects.md);
status wording alone is not evidence of settlement. The service and active-case
uniqueness guard duplicate intake; PostgreSQL acceptance-contention and complete
browser/hosted acceptance remain unverified. Resolved card transactions can be
disputed again under the current policy.

Even if specific to banking scenarios, this sample can be used for other business use cases as technical reference architecture concerning customer support chatbots or virtual assistants using Microsoft Agent Framework to implement supervisor based orchestration for multiple domains agents that need to integrate with business domains API through MCP. AI-powered assistants in other domains by adapting the agents tools and backend services to your specific business needs.

<div align="center">
  
[**BUSINESS SCENARIO**](#business-scenario)  \| [**SOLUTION OVERVIEW**](#solution-overview) \| [**SUPPORTING DOCUMENTATION**](#supporting-documentation)

</div>
<br/>

**Note:** With any AI solutions you create using these templates, you are responsible for assessing all associated risks and for complying with all applicable laws and safety standards. Learn more in the transparency documents for [Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/responsible-ai/agents/transparency-note) and [Agent Framework](https://github.com/microsoft/agent-framework/blob/main/TRANSPARENCY_FAQ.md).
<br/>

<h2><img src="./docs/assets/business-scenario.png" width="48" />
Business scenario
</h2>

Users can converse with the assistant to inquire about account balances and review recent transactions instead of navigating traditional menus. The active workflow does not execute payments.

The dashboard presents an owned-product catalog with All, Accounts, and Cards
filters. Selecting a product opens `/product/:productId`, where date and movement
filters, totals, and transaction history are scoped to that product. The standalone
movement-analysis navigation is retired; `/analytics` redirects to the catalog.
Product detail reuses the card-style summary for accounts and cards. Standalone
Cards and Investments pages are removed; `/credit-cards` and `/portfolio` redirect
to the catalog. Card numbers display the first and last four digits with the middle
masked; existing last-four-only masks remain unchanged.
New support-case disputes are restricted to card transactions by the Transaction
service; existing account cases remain readable. No card-to-account association is
inferred. Account and card summaries expose an opaque `product_id`; card numbers
remain masked. JWT-authenticated card history uses
`GET /api/transactions/products/{product_id}/history`; bank account history retains
`GET /api/transactions/{product_number}/history`. Both support inclusive date
filters and pagination, and enforce customer ownership.

The submission MVP extends this flow into support operations: users can open a
transaction-dispute support case from conversation context or directly from a
transaction row, track intake and consent through
`OPEN -> WAITING_USER_APPROVAL -> IN_REVIEW`, approve or decline review consent,
and receive a single contextual product recommendation with an explicit opt-out
only after case resolution. Customer approval
starts review: all fraud-score classifications remain `IN_REVIEW`, including low
scores, until an explicit resolution operation. A low stored score is routing
information, not a legitimacy verdict or authorization for automatic closure.
Real operators claim consented, unclaimed cases exclusively and rediscover their
assigned cases after refresh at `/operator/support-cases`. Owner-only detail shares
the customer timeline with operator-perspective wording and localized timestamps.
The simulated ServiceAgent catalog is retired; archived assignments never become
real ownership. Assigned operators submit reasoned, versioned verdicts: invalid cases
become `RESOLVED_INVALID`; valid cases remain `PENDING_EFFECTS` until an atomic
compensation posting and balance adjustment succeed, then become `RESOLVED_VALID`.
Debit compensation prefers owned active same-currency savings accounts, then checking
accounts; credit compensation reduces card debt. Card protection is a separate audited
application action, not external processor enforcement. Customer resolution authority
is retired; historical resolved cases are not automatically reopened or compensated.
Reassignment and review timeouts remain unavailable. Local migration
`20261004_0011` was applied and its head verified on authorized localhost PostgreSQL;
six isolated PostgreSQL concurrency/rollback regressions passed. Browser and hosted
acceptance remain separate gates. See the
[frontend guide](app/frontend/banking-web/README.md#transaction-disputes) and
[business API guide](app/business-api/README.md) for the implementation.

The Account and Transaction APIs read PostgreSQL through shared SQLModel and enforce resource ownership. [Identity](./app/business-api/identity/README.md) owns credentials, profiles, customer/operator/admin roles and identity lifecycle. The database-free [Responses BFF](./app/responses-bff/README.md) fronts allowlisted identity/admin operations and customer Responses chat. Financial REST calls remain direct, with the same application JWT and per-request current-identity checks. Staff cannot access customer financial REST or chat. See [ADR 0006](./docs/adr/0006-dedicated-auth-users-and-staff-identities.md); live migration, provisioning and browser validation remain separate gates.

### Evaluation Status

The implemented dispute workflow and its evaluation evidence are separate:

- [Dispute service tests](app/business-api/transaction/tests/test_dispute_service.py)
  cover deterministic business behavior against seeded fixtures, not real-model
  quality or deployed data parity.
- The [18 held-out scenarios](evals/scenarios.json) target transaction disputes,
  but a complete proposed-system run is not yet verified. The current live runner
  uses final-text heuristics, not persisted-state verification.
- The [isolated MCP replay](evals/README.md#isolated-mcp-replay) uses the production
  workflow with synthetic tools and a real model when executed. Its three current
  cases are Account/Transaction smoke checks, not dispute workflow evaluations;
  [CI run 37089481802](https://github.com/cristofima/factored-hackathon-2026-cristopher-coronado/actions/runs/37089481802)
  verified 3/3 protocol cases with real-model execution, OIDC and artifacts.
  The [PR protocol smoke check](evals/README.md#pr-smoke-check)
  has a persistent comment and transcript artifacts; dispute quality
  and baseline comparison remain pending.

[ADR 0009](docs/adr/0009-operator-verdicts-with-recorded-financial-effects.md)
records the approved assigned-operator verdict and actual-compensation contract,
including savings/checking allocation for debit disputes. Versioned evidence,
financial execution and duplicate-compensation protection are implemented with
synthetic automated coverage and isolated localhost PostgreSQL concurrency/rollback
checks. The local migration is applied; browser, real-data parity and hosted runtime
acceptance remain separate verification gates. Existing review claims alone do not settle a dispute or change
card state.
Dispute-specific evaluation remains a separate priority for intake, customer approval,
low/high/missing-score review, safe refusals and grounded status explanations.
Service authorization and persisted timelines require independent integration
checks. See the [evaluation guide](evals/README.md) for coverage and limitations.

Business-impact reporting will distinguish safely completed cases from simple
containment and correct escalation. No measured reduction in support workload or
cost is claimed; economic estimates require explicit volume, handling-time, and
cost assumptions, which are not established by transaction activity alone.

The hackathon also requires baseline-versus-proposed comparison on the same
held-out workload and baseline evidence for a learned component. The current
label-derived policy simulation is not an executed comparator. A separate executable
rules-based comparator passes 25 development-exposed synthetic cases, with multi-turn
scoring and saved-report comparison. A paired real-model run on a shared frozen
workload remains pending; no improvement is claimed. Fraud-score threshold analysis
is separate from that comparison.

### Key Features

<details open>
  <summary>Click to learn more about the key features this solution enables</summary>
 
 - **Add an agentic conversational experience to your existing website** <br/>
The React frontend streams OpenAI Responses events for account and transaction inquiries through a JWT-protected BFF.
 - **Multi-agent supervisor architecture** <br/>
 Use handoff orchestration to understand user intent and delegate requests to domain agents. The hosted-agent manifest declares **gpt-4.1-mini** on [Microsoft Foundry](https://azure.microsoft.com/en-us/products/ai-foundry); this repository does not provision the model deployment.
 - **Reusing existing business APIs as MCP tools** <br/>
 Business service logic is exposed to agents through MCP using [fastmcp](https://gofastmcp.com/getting-started/welcome) 
 - **Microsoft Agent Framework First** <br/>
 Use [MAF](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview) chat agents to flexibly support AzureOpenAI or Foundry Agent Service based agents
 - **Human-In-The-Loop (HITL) patterns** <br/>
 The transaction-dispute support case gates on a real customer approval step before
 entering deterministic review and permitting an exclusive real-operator claim,
 backed by a persisted case/event audit trail, not just generic protocol approvals.
 Banking inputs are synthetic; customer consent and review ownership are persisted.
 Claim is not adjudication, and case closure does not post credit, change balances
 or protect a card. Historical ServiceAgent assignments remain archived only.
- **Separate hosted agent and App Services** <br/>
The Foundry hosted agent uses its own azd project; the root Terraform stack defines five App Services for Identity, the BFF, web frontend, and business APIs.
- **Automated IaC and App build & Deployment**
Automated Azure resources creation and solution deployment leveraging [Azure Developer CLI](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/).

</details>
<br/>

<h2><img src="./docs/assets/solution-overview.png" width="48" />
Solution overview
</h2>

### Solution architecture

| ![image](docs/assets/HLA-Agent-Framework.png) |
| --------------------------------------------- |

The home banking assistant uses a handoff workflow whose agents specialize in account and transaction inquiries. Business service logic is exposed to those agents through MCP endpoints. The browser sends OpenAI Responses requests with a bearer JWT to the BFF. The BFF validates the user, signs downstream identity, and routes the request to the local Responses agent or, when configured, obtains an Azure access token and calls the Foundry-hosted agent.

### Additional resources

- [Architecture](./ARCHITECTURE.md)
- [Architecture Decision Records](./docs/adr/README.md)
- For Semantic Kernel version check this [branch](https://github.com/Azure-Samples/agent-openai-python-banking-assistant/tree/semantic-kernel)

### Prerequisites

- [Python >= 3.11](https://www.python.org/downloads/release/python-31113/)
- [uv](https://github.com/astral-sh/uv)
- [Azure Developer CLI](https://aka.ms/azure-dev/install)
- [Node.js](https://nodejs.org/en/download/)
- [Git](https://git-scm.com/downloads)
- [Powershell 7+ (pwsh)](https://github.com/powershell/powershell) - For Windows users only.
  - **Important**: Ensure you can run `pwsh.exe` from a PowerShell command. If this fails, you likely need to upgrade PowerShell.

> [!WARNING]
> Your Azure Account must have `Microsoft.Authorization/roleAssignments/write` permissions, such as [User Access Administrator](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles#user-access-administrator) or [Owner](https://learn.microsoft.com/azure/role-based-access-control/built-in-roles#owner).

Clone this repository and select an azd environment. Before provisioning the root stack, prepare an existing resource group and Terraform remote-state storage as described in [Terraform provisioning](./infra/README.md). Import existing resources and review the Terraform plan before provisioning a previously deployed environment.

### Deploy targets in this repository

This repository intentionally uses two separate Azure Developer CLI project roots:

- Root project (`./azure.yaml`): Terraform provisions the shared Linux plan, five App Services (Identity, Account, Transaction, Responses BFF, web), monitoring, Blob storage, and a dedicated Foundry account and project; root `azd deploy` deploys only the App Service workloads. All five services use explicit `resourceName` bindings to Terraform app-name outputs; each CD workflow requires its corresponding GitHub Development name variable. See the [infrastructure guide](./infra/README.md) for coordinated secrets, rollout and rollback.
- Agent project (`./app/agent/azure.yaml`): the `microsoft.foundry` provider deploys the hosted agent to the existing Foundry project. Set its `FOUNDRY_PROJECT_ENDPOINT` from the root environment output before deploying; the two azd environments are separate.

Naming note for the App Service stack: the frontend app uses `app-banking-web-<env>` (for example, `app-banking-web-development`) so the web workload name is explicit and distinct from backend services.

Configure these GitHub Variables in the `Development` environment using the physical
App Service names from Terraform outputs. Terraform does not publish them to GitHub:

| Service       | GitHub Variable                | Terraform output / azd variable |
| ------------- | ------------------------------ | ------------------------------- |
| Identity      | `AZURE_IDENTITY_APP_NAME`      | `AZURE_IDENTITY_APP_NAME`       |
| Account       | `AZURE_ACCOUNT_APP_NAME`       | `AZURE_ACCOUNT_APP_NAME`        |
| Transaction   | `AZURE_TRANSACTION_APP_NAME`   | `AZURE_TRANSACTION_APP_NAME`    |
| Responses BFF | `AZURE_RESPONSES_BFF_APP_NAME` | `AZURE_RESPONSES_BFF_APP_NAME`  |
| Web           | `AZURE_WEB_APP_NAME`           | `AZURE_WEB_APP_NAME`            |

CD exports each GitHub value under the same `_APP_NAME` azd variable used by `resourceName`;
Python preflight checks the same named app. Tags are metadata, not selectors.
These names are deployment configuration, not URLs or secrets. Consume actual
hostname outputs for service URLs. See the [workflow guide](./.github/workflows/README.md#required-github-environment-variables)
for shared configuration.

Use these commands from the repository root:

```shell
# Provision the App Service and dedicated Foundry resources after remote state setup and plan review
azd provision
azd deploy

# Configure and deploy the separate hosted-agent project after local agent validation
# azd env set FOUNDRY_PROJECT_ENDPOINT <root FOUNDRY_PROJECT_ENDPOINT> --cwd app/agent
azd up --cwd app/agent
```

For iterative agent updates only:

```shell
azd deploy --cwd app/agent
```

### Python dependency artifact for App Service zip deploy

Identity, the two Python MCP APIs (`account`, `transaction`), and the Responses BFF are deployed independently from the root `azure.yaml`. For App Service zip deploy, each Python service directory must include its own `requirements.txt` so Oryx can install runtime dependencies. Keep `pyproject.toml` and the `uv` lock files as the development source of truth and regenerate `requirements.txt` before deployment changes.

```shell
uv pip compile app/business-api/account/pyproject.toml --no-emit-package banking-shared -o app/business-api/account/requirements.txt
uv pip compile app/business-api/transaction/pyproject.toml --no-emit-package banking-shared -o app/business-api/transaction/requirements.txt
uv pip compile app/business-api/identity/pyproject.toml --no-emit-package banking-shared --python-version 3.11 --python-platform x86_64-unknown-linux-gnu -o app/business-api/identity/requirements.txt
uv export --project app/responses-bff --no-dev --no-hashes --no-emit-project --no-emit-package banking-shared --output-file app/responses-bff/requirements.txt
```

Account, Transaction and Identity consume the canonical SQLModel package from `app/business-api/shared`; the database-free BFF still uses shared identity/model code. Root `azd` packaging hooks copy the shared package into isolated App Service zips and remove temporary copies afterward. Identity's [CI/CD workflows](./app/business-api/identity/README.md#cicd) use the root manifest and Linux Python 3.11 `uv pip compile` runtime requirements. Root Terraform declares its dedicated App Service; root azd and standalone CD target its explicit `AZURE_IDENTITY_APP_NAME`, like the other four services. Hosted rollout and full artifact/startup acceptance remain unverified. The `--no-emit-package` option keeps machine-local editable paths out of Oryx artifacts.

Foundry Responses maintains conversation history when requests link turns with a signed user-bound `conversation` value. The BFF rejects conversation identifiers that belong to a different authenticated user. Identity verifies Argon2 credentials and issues short-lived HS256 JWTs; the BFF checks current active identity and version through protected introspection.

The local Responses host creates an independent workflow per request and restores the
matching conversation checkpoint when present. The installed hosting SDK persists
local checkpoints as JSON under `~/.agentserver/state_stores`, unless
`AGENTSERVER_STATE_ROOT` overrides the root. Browser threads exist only in React state:
a reload clears the thread, and its first message creates a new user-bound conversation.

For more info about deployment click [here](./docs/deployment-guide.md)

🛠️ **Need Help?** Check our [Troubleshooting Guide](./docs/troubleshooting.md) for solutions to common deployment issues.
<br/><br/>

### Prerequisites and costs

Pricing varies per region and usage, so it isn't possible to predict exact costs for your usage.
However, you can try the [Azure pricing calculator](https://azure.com/e/8ffbe5b1919c4c72aed89b022294df76) for the resources below.

- Azure App Service: a shared Linux plan for the four apps. [Pricing](https://azure.microsoft.com/en-us/pricing/details/app-service/linux/)
- Azure Blob Storage: Standard LRS. [Pricing](https://azure.microsoft.com/pricing/details/storage/blobs/)
- Azure Monitor: Log Analytics and Application Insights, billed by usage. [Pricing](https://azure.microsoft.com/en-us/pricing/details/monitor/)
- The separate Foundry project and model usage have their own costs.

Do not run `azd down` against an existing shared resource group as a rollback strategy; review the Terraform plan and resource ownership first.

### Local development (VS Code)

Start Identity (8090), Account MCP (8070), Transaction MCP (8071), local Responses agent (8088), Responses BFF (8080) and Vite (5170). Configure `AUTH_USERS_ENDPOINT=http://127.0.0.1:8090`, a separate `AUTH_INTERNAL_SECRET`, and shared JWT secret/issuer/audience for Auth, BFF and financial REST callers. Auth, Account and Transaction need the approved PostgreSQL configuration; the BFF must not receive database configuration or permissions. Local BFF uses `RESPONSES_UPSTREAM_MODE=local`; browser chat never calls Foundry directly.

Each service owns its ignored `.env` and credential-free `.env.example`; there is no root dotenv configuration. BFF, Account and Transaction use `AUTH_USERS_ENDPOINT` to reach Identity. The frontend uses the BFF URL for authentication and administration and does not need a direct Identity URL.

In VS Code, `F5` with `DEV - Full Stack Ordered` starts all six services in separate terminals and opens `http://localhost:5170/`. The user confirmed this local startup works. Approved migrations and administrator bootstrap were executed during local setup; startup itself never seeds an administrator. This evidence does not establish hosted rollout or the complete authorization matrix.

### Administrator workspace

Administrators manage operators at `/admin/operators` and create them on the protected `/admin/operators/create` page. `/admin/customers` lists existing customer identities and allows activation/deactivation; it does not load customer data or create public registrations. Both lists display persisted `active`/`inactive` status and `updated_at`. Status changes revoke existing tokens through identity-version checks.

The workspace reuses the customer frontend's shared components and styles, with contrasting navigation tabs and centered AlertDialog confirmation modals. Operator creation remains a separate page. The user confirmed local UI validation; focused administrator/routing tests passed (51 tests), lint had zero errors and 14 existing warnings, and the frontend build passed. Real reviewer queues and dispute decisions remain disabled in the `/operator` placeholder. See the [Identity guide](./app/business-api/identity/README.md) and [frontend guide](./app/frontend/banking-web/README.md).

### Customer identity provisioning

The [data pipeline](./app/business-api/data/README.md) loads banking customers, products and transactions, not login identities. The separate [demo user seeder](./app/business-api/data/README.md#seed-demo-users) creates or refreshes selected customer identities as active, rotating credentials and identity version on refresh. Normal ingestion does not change login status.

Explicit customer seeding copies Customer `first_name`/`last_name` into User `name` on creation and refresh, trimming each component and joining nonempty components with one space. If both are absent or blank, the stored name is null and the frontend uses its email fallback. This producer fix does not backfill existing identities: live database writes require separate authorization, and refresh also rotates credentials, activates selected users, and revokes existing tokens.

The BFF exposes the protected Responses endpoint at `http://localhost:8080/responses`; the local agent listens at `http://localhost:8088/responses`.

For local Azure OpenAI inference with `PROFILE=dev`, sign in with `az login` using an identity that has the `Cognitive Services OpenAI User` role on the configured Azure AI Services resource. Create approved persisted test identities through the [demo user seeder](./app/business-api/data/README.md#seed-demo-users) and sign in through the frontend. Do not substitute a fixed development bearer token.

<h2><img src="./docs/assets/supporting-documentation.png" width="48" />
Supporting documentation
</h2>

### Restrict access to the public web app

The root Terraform stack does not configure network access restrictions for the public web app. Prototype JWT authentication and persisted ownership checks exist, but do not expose real customer data until hosted identity transport, deployment controls, and the complete authorization validation matrix are verified.

### Prototype limitations

This repository is a hackathon prototype. It demonstrates an architecture pattern and deployment topology, but it does not claim production-ready controls for a regulated banking environment.

Current limitations to keep explicit:

- End-user login uses PostgreSQL-backed Argon2 identities and short-lived JWTs; it is not a production identity lifecycle.
- The frontend displays persisted customer names and owned accounts, including explicit multi-account selection. Account codes absent from the schema are omitted; Agreements and Privacy & Security Policy remain inherited placeholders.
- Dashboard and Analytics consume Account and Transaction directly over JWT-authenticated REST, with fully paginated transactions. Credit/debit cards use a customer-scoped, read-only catalog with server-masked numbers; card operations remain unavailable. See the [frontend guide](app/frontend/banking-web/README.md) for presentation and validation limits.
- Account and Transaction use persisted product ownership and transaction rows. Selected local two-user PostgreSQL and browser financial comparisons passed, but the complete signed agent-chain, browser-state, and deployed validation matrices remain open.
- Signed stored-locale context and profile-bound frontend i18n support exact `es`, `pt`, and `en`, with English fallback. Static JSON catalogs translate UI and transaction labels, including Card/Tarjeta/Cartão; Spanish generated/display text uses reclamo/reclamos while canonical contracts, customer reasons and audit text remain unchanged. Controlled BFF failures use localized UI messages, while login stays English. Product queries use canonical English labels and ingestion normalizes Spanish source values. Automated coverage does not establish authenticated browser localization, multilingual agent conversations, or hosted parity. See the [localization guide](app/frontend/banking-web/README.md#localization).
- On 2026-09-30, user-supplied local browser evidence confirmed an owned-account answer with full bank number and masked card output, and a foreign-account lookup returning `ACCESS_DENIED` followed by a visible assistant response. This closes the reported blank-response failure, not the full authorization or hosted matrix; the complete real-data verification checklist is tracked internally, not in this public repository.
- MCP and internal API authorization must be enforced in service code (`customer_id` ownership checks), not inferred from prompts.
- The frontend must not call Foundry or agent endpoints directly; browser traffic for the chat path must go through the Responses BFF. Account and Transaction reads are the one scoped exception: the frontend calls those two services directly, authenticated with the same application JWT Identity issues.
- The BFF validates application identity and proxies upstream requests, but this does not replace per-resource authorization in business services.
- The previous ChatKit-style direct browser-to-agent pattern is no longer the target architecture.
- HITL proposal widgets require explicit customer consent before transaction-dispute
  case creation. Read-only preview and decline create no case/events; acceptance
  atomically records intake, consent and deterministic routing in `IN_REVIEW`.
  Legacy pending cases retain their approval path, and REST-accepted cases continue
  in chat through readback without second consent. See the
  [consent contract](app/business-api/transaction/README.md#customer-dispute-proposal-and-consent).
  Exclusive real operator claims and a single post-resolution recommendation with
  opt-out remain separate workflow steps. Simulated assignments are archived only. Assigned-operator adjudication and
  atomic compensation are implemented, with separately audited local card protection;
  browser and hosted acceptance remain unverified. The 365-day dispute window
  is a demo policy evaluated against the real system clock and will reject opening new
  disputes once the loaded dataset's transactions fall outside it.
- Prompt-injection resilience is bounded by deterministic authorization checks and does not rely on model instruction following alone.
- Logging and tracing are useful for diagnostics, but sensitive-data controls and retention governance must be reviewed before production.

Production controls that remain outside this prototype scope:

- Enterprise IAM integration (full account lifecycle, MFA, password reset, session revocation, key rotation).
- End-to-end network isolation (private endpoints, restricted ingress, and explicit east-west trust boundaries).
- Complete compliance controls (PCI-DSS, GDPR, local banking regulation mapping, evidence collection, and formal audit workflows).
- Fraud and abuse controls (risk scoring, anomaly detection, velocity rules, and adaptive step-up authentication).
- Operational resilience standards (disaster recovery objectives, multi-region failover, and formal incident response playbooks).
- Full security verification program (penetration testing, dependency governance, SAST/DAST tuning, and continuous control validation).

In short: the intended secure pattern is `frontend -> BFF -> hosted agent -> authenticated MCP/APIs`, with authorization checks in each business service. The prototype already aligns to that direction, and remaining phases close the gaps.

### Security guidelines

> [!IMPORTANT]
> **This sample is a proof-of-concept. Its prototype authentication and authorization controls are not production-ready.**

The sample does not cover the following aspects, essential to the security of the solution:

- **Identity rollout pending**: Identity implements Argon2 login, fixed staff roles, operator password/status changes and per-request version revocation. Public registration and MFA are not implemented. Synthetic tests do not prove live migrations, least-privilege grants, browser isolation or deployed rollback; existing role-less tokens require fresh login.
- **Local identity chain only**: Signed BFF-to-agent identity and 60-second agent-to-MCP bearers are validated locally. Hosted delegated-identity transport remains unverified.
- **Persisted ownership checks**: Account and Transaction service methods enforce `customer_id` ownership through PostgreSQL product relationships and transaction-row filters. Hosted transport and full browser scenario validation remain pending.
- **Conversation binding is application-scoped**: The BFF binds conversation identifiers to verified JWT subjects, but production persistence, lifecycle, and hosted isolation still require validation.

When deploying to production with real customer data, consider implementing:

- **End-user authentication and authorization integrated with your identity provider**
- **Conversation and data isolation per user and per account**
- **Audit logging of all access and operations**
- **Compliance with applicable regulations (PCI-DSS, GDPR, local banking regulations)**

### Resources

Here are some resources to learn more about multi-agent architectures and technologies used in this sample:

- [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
- [AI agents For Beginners](https://github.com/microsoft/ai-agents-for-beginners)
- [Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/what-is-azure-ai-foundry)
- [Develop AI apps using Azure services](https://aka.ms/azai)
- [Building Effective Agents - Anthropic](https://www.anthropic.com/engineering/building-effective-agents)
- [AI agent orchestration patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)

You can also find [more Microsoft Foundry agents samples here](https://aka.ms/aiapps)
