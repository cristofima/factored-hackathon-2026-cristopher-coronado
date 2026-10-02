# Repository Guide

This repository is a banking-assistant prototype built with Python, Microsoft Agent Framework, Foundry Responses, FastMCP, React, and Terraform.

## Active Architecture

```mermaid
flowchart LR
    Browser[React banking web] -->|chat| BFF[Responses BFF]
    BFF --> Agent[Responses agent]
    Agent --> Account[Account MCP]
    Agent --> Transaction[Transaction MCP]
    Browser -->|accounts, cards, transactions, disputes| Account
    Browser -->|accounts, cards, transactions, disputes| Transaction
```

- `app/agent`: Account/Transaction handoff workflow and Responses host.
- `app/responses-bff`: application JWT boundary and Responses proxy, scoped to identity
  (`/auth/login`, `/auth/me`) and fronting the agent only; it does not read account, card,
  or transaction data.
- `app/business-api/account`: Account REST and MCP service. Its REST endpoints verify the
  browser's application JWT directly (`jwt_identity.py`); its MCP tools verify a separate
  short-lived agent-only bearer (`internal_identity.py`).
- `app/business-api/transaction`: Transaction REST and MCP service, same dual-auth split
  as Account.
- `app/business-api/data`: SQLModel/Alembic schema and verified CSV-to-PostgreSQL pipeline.
- `app/frontend/banking-web`: React/Vite banking UI, calling Account/Transaction directly
  for financial data and the Responses stream through the BFF for chat. Includes the
  transaction-dispute support-case pages (`/support-cases`, `/support-cases/:caseId`,
  `ReportDisputeDialog`), calling Transaction's `/api/support-cases` directly with the
  same application JWT, never through the BFF.
- `infra`: Terraform for the App Service stack and Foundry resources.
- `app/agent/azure.yaml`: separate azd root for the hosted Foundry agent.

## Security Boundaries

- The browser calls the BFF for chat and never calls Foundry or the local agent directly.
  For account, card, transaction, and support-case reads, the browser calls Account and
  Transaction directly instead, authenticated with the same application JWT the BFF issues;
  this is the one scoped exception to the BFF-only rule.
- The BFF authenticates PostgreSQL-backed Argon2 users, issues short-lived application JWTs,
  validates those JWTs for its own two routes, and obtains Azure credentials server-side. Its
  [service guide](app/responses-bff/README.md) documents login and profile only; it no longer
  reads account/card/transaction data.
- Conversation ownership is bound to the verified JWT subject.
- The BFF signs verified `sub` and `customer_id` claims for the agent. The agent verifies that envelope and issues a fresh 60-second bearer for Account and Transaction MCP calls. This chain is validated locally; hosted transport behavior still requires proof.
- Account and Transaction independently verify the browser's application JWT for their REST
  endpoints (`jwt_identity.py`, same HS256 secret/issuer/audience as the BFF) and enforce
  customer-resource ownership in `services.py` through PostgreSQL product relationships and
  transaction filters. This is a separate auth dependency from the MCP-only
  `internal_identity.py` bearer; never conflate the two. CORS is enabled via
  `CORS_ALLOWED_ORIGINS` on both services.
- Persisted users, customer names, owned-account selection and signed profile/locale injection are implemented. Actual multilingual conversations and hosted identity transport validation remain pending. Do not add fixed tokens, `MOCK_SESSION_TOKEN`, fabricated claims, or a second login mechanism.
- Never log JWTs, passwords, bearer tokens, or Azure credentials.

## Local Development

The root `.vscode` configuration owns local orchestration. `DEV - Full Stack Ordered` starts:

| Port   | Process               |
| ------ | --------------------- |
| `5170` | Banking web           |
| `8080` | Responses BFF         |
| `8088` | Local Responses agent |
| `8070` | Account MCP           |
| `8071` | Transaction MCP       |

Use the browser through this topology for local validation. Hosted Foundry deployment is a later, separate validation target.

## Data Ingestion

Use `app/business-api/data/scripts/run_pipeline.py` for normal data loads. It runs EDA,
scope selection, loading, and verification in order. The
[data module guide](app/business-api/data/README.md) is the source of truth for detailed
operation. Invoke it from the repository root with the data project's ignored `.env` file
and an explicit inclusive date window:

```powershell
uv run --project app/business-api/data --env-file app/business-api/data/.env python app/business-api/data/scripts/run_pipeline.py --start-date 2026-06-01 --end-date 2026-06-01 --customer-ids CUSTOMER_A,CUSTOMER_B,CUSTOMER_C
```

- `--customer-ids` is optional and is one comma-separated string. Whitespace and duplicates
  are normalized internally; demo loads should use at most three customers.
- Customer filtering applies to `customers`, `products`, and transactions in the selected
  date window. `branches` and `service_agents` remain complete shared catalogs.
- The loader validates requested customers and product ownership before committing selected
  transactions. It never populates `users`.
- Dimensions commit first. Each transaction day then commits or rolls back independently,
  and later days continue after a failed day.
- Treat the generated load manifest as the source of truth for checksums, processed counts,
  customer scope, daily outcomes, and verification. Filtered artifact names include a stable
  customer count/hash suffix.
- Keep `DATABASE_URL`, `DATA_SOURCE_DIR`, `DATA_ARTIFACTS_DIR`, and `DATA_MANIFEST_DIR` in the
  ignored data `.env`; never print credentials.

## Development Rules

- Read `plan/README.md` and `plan/00-decisions.md` before non-trivial changes.
- Keep `plan/` local-only and never stage or commit it.
- Use Python 3.11+, modern type annotations, async I/O, and `uv`.
- Keep MCP tools thin; put business logic and authorization in service modules.
- Keep agent instructions and tool schemas in English. The profile provider uses signed per-request `locale` (`es`, `pt`, `en`, otherwise `en`) for response language. Do not infer it from messages or checkpoint state.
- Preserve the separate root App Service and `app/agent` hosted-agent azd projects.

## Focused Checks

```powershell
cd app/agent
uv run pytest tests/test_hosted_workflow.py tests/test_settings.py -q

cd ../responses-bff
uv run pytest -q

cd ../business-api/account
uv run --directory . python -m pytest tests -q

cd ../transaction
uv run --directory . python -m pytest tests -q

cd ../../frontend/banking-web
npm run lint
npm run build

cd ../../business-api/data
uv run pytest tests/test_run_pipeline.py -q
```

Run `terraform fmt -check -recursive` and `terraform validate` from `infra` after infrastructure changes.
