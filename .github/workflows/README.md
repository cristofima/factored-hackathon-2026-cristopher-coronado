# CI/CD Workflows

This directory contains the GitHub Actions workflows for CI and CD. Infrastructure is provisioned separately, and deployments here only run `azd deploy` for already-provisioned services.

Reusable building blocks live in [../actions](../actions):

- [../actions/ci-python/action.yml](../actions/ci-python/action.yml): shared Python CI implementation used by all `ci-*` workflows.
- [../actions/ci-node/action.yml](../actions/ci-node/action.yml): shared Node/React CI implementation used by frontend `ci-*` workflows.
- [../actions/cd-azure/action.yml](../actions/cd-azure/action.yml): shared Azure login and `azd` environment setup used by all `cd-*` workflows.

## Naming convention

- `ci-*.yml`: validation workflows for each service (Python and frontend).
- `cd-*.yaml`: deployment workflows for each deployable service.

## Deployment model

- Target branch: `main`
- Target GitHub Environment: `Development`
- Authentication: GitHub OIDC with `azure/login@v2`
- Provisioning in CI: not allowed (`azd provision` is intentionally not used here)
- Deploy command pattern: `azd deploy <service> --no-prompt`
- CD triggers: push to `main` on matching path filters; manual dispatch where enabled.

## CI model

- CI branches: `main`, `develop`, `feature/*`, `refactor/*`.
- PR targets: `main`, `develop`.
- Common checks per project: dependency sync with `uv`, compile check, test discovery, pytest when tests exist, and artifact upload (`junit.xml`, optional `coverage.xml`).
- Frontend checks: `npm ci`, `lint`, tests with Vitest coverage summary/artifact, and production `vite build` via shared `ci-node`.
- Frontend Node runtime: shared `ci-node` defaults to Node `22`.

## Workflow inventory

| Workflow file           | Purpose                                 | Trigger path                           | azd project root | Main command                                             |
| ----------------------- | --------------------------------------- | -------------------------------------- | ---------------- | -------------------------------------------------------- |
| `ci-account.yml`        | Validate Account API Python build/tests | `app/business-api/account/**`          | n/a              | Shared action (`ci-python`)                              |
| `ci-transaction.yml`    | Validate Transaction API build/tests    | `app/business-api/transaction/**`      | n/a              | Shared action (`ci-python`)                              |
| `ci-payment.yml`        | Validate Payment API build/tests        | `app/business-api/payment/**`          | n/a              | Shared action (`ci-python`)                              |
| `ci-responses-bff.yml`  | Validate Responses BFF build/tests      | `app/responses-bff/**`                 | n/a              | Shared action (`ci-python`)                              |
| `ci-hosted-agent.yml`   | Validate hosted-agent build/tests       | `app/agent/**`                         | n/a              | Shared action (`ci-python`)                              |
| `ci-data.yml`           | Validate data module build/tests        | `app/business-api/data/**`             | n/a              | Shared action (`ci-python`)                              |
| `ci-frontend.yml`       | Validate frontend lint/tests/build      | `app/frontend/banking-web/**`          | n/a              | Shared action (`ci-node`)                                |
| `cd-account.yaml`       | Deploy Account API App Service          | `app/business-api/account/**`          | repository root  | `azd deploy account --no-prompt`                         |
| `cd-transaction.yaml`   | Deploy Transaction API App Service      | `app/business-api/transaction/**`      | repository root  | `azd deploy transaction --no-prompt`                     |
| `cd-payment.yaml`       | Deploy Payment API App Service          | `app/business-api/payment/**`          | repository root  | `azd deploy payment --no-prompt`                         |
| `cd-responses-bff.yaml` | Deploy JWT-protected Responses BFF      | `app/responses-bff/**`                 | repository root  | `azd deploy responses-bff --no-prompt`                   |
| `cd-frontend.yaml`      | Deploy frontend Web App Service         | `app/frontend/banking-web/**`          | repository root  | `azd deploy web --no-prompt`                             |
| `cd-hosted-agent.yaml`  | Deploy Foundry hosted agent             | `app/agent/**` and `workflow_dispatch` | `app/agent`      | `azd -C app/agent deploy home-banking-agent --no-prompt` |

## Why two azd project roots exist

This repository uses two independent `azure.yaml` manifests:

1. Root [azure.yaml](../../azure.yaml): App Service stack (`account`, `payment`, `transaction`, `responses-bff`, `web`).
2. Agent [azure.yaml](../../app/agent/azure.yaml): Foundry hosted-agent stack (`home-banking-agent`).

For that reason, `cd-hosted-agent.yaml` always uses `azd -C app/agent ...` so it resolves the agent manifest explicitly and never the root manifest.

## Required GitHub Environment variables

Set these in **Settings > Environments > Development > Variables**.

### Shared variables (all workflows)

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_LOCATION`
- `AZURE_RESOURCE_GROUP`

### Shared application JWT secret (`cd-responses-bff.yaml`, `cd-account.yaml`, `cd-transaction.yaml`)

Set `RESPONSES_BFF_JWT_SECRET` under **Settings > Environments > Development > Secrets**.
It must contain at least 32 characters. The BFF signs the browser's application JWT with
this value; Account and Transaction verify that same JWT directly for their REST endpoints,
so all three workflows write it to their own App Service as `JWT_SECRET_KEY` without
printing it. Keep the value identical across all three. Terraform and `azd` environment
state never contain it. Terraform configures the BFF `DATABASE_URL` for the shared
PostgreSQL database and sets Account/Transaction's `DATABASE_URL`/`CORS_ALLOWED_ORIGINS`
directly (no secret involved); `cd-account.yaml`/`cd-transaction.yaml` only verify those
two settings already exist on the target App Service before deploying (failing fast with
a `azd provision` hint if Terraform hasn't run yet) and never set or overwrite them.

### Internal identity secret

Set `INTERNAL_IDENTITY_SECRET` under **Settings > Environments > Development > Secrets**. Use the same value, with at least 32 characters, for the BFF, hosted agent, Account API, and Transaction API workflows. Each workflow injects it into its deployment target without printing it. Terraform intentionally does not manage this value, so it cannot enter Terraform state.

### Hosted-agent variables (`cd-hosted-agent.yaml`)

`app/agent/azure.yaml` substitutes `${ACCOUNT_MCP_URL}`/`${TRANSACTION_MCP_URL}` at deploy
time, so set both under **Settings > Environments > Development > Variables** to the
deployed Account/Transaction App Service MCP endpoints
(`https://<app-hostname>/mcp`), alongside the other required variables below. The workflow
validates and injects them with `azd -C app/agent env set` the same way as the rest of this
list.

Required:

- `FOUNDRY_PROJECT_ENDPOINT`
- `AZURE_AI_PROJECT_ID`
- `MODEL_DEPLOYMENT_NAME`
- `ACCOUNT_MCP_URL`
- `TRANSACTION_MCP_URL`

Optional (observability and tracing behavior):

- `ENABLE_INSTRUMENTATION`
- `ENABLE_SENSITIVE_DATA`
- `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING`
- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`

## Hosted-agent workflow details

`cd-hosted-agent.yaml` performs these steps:

1. Installs Foundry `azd` extension (`microsoft.foundry`) in the runner.
2. Authenticates with Azure via OIDC.
3. Creates/selects `development` `azd` environment in `app/agent`.
4. Validates required Foundry variables before deployment.
5. Sets environment variables with `azd -C app/agent env set ...`.
6. Deploys only `home-banking-agent`.
7. Prints agent status with `azd -C app/agent ai agent show --no-prompt`.

## Responses BFF workflow details

`cd-responses-bff.yaml` performs these steps:

1. Authenticates with Azure via OIDC and selects the root `development` azd environment.
2. Validates `RESPONSES_BFF_JWT_SECRET` without printing it.
3. Writes `JWT_SECRET_KEY` directly to the provisioned BFF App Service.
4. Deploys only `responses-bff`.

The BFF App Service uses its system-assigned managed identity to call Foundry. Terraform grants that identity the built-in `Foundry Agent Consumer` role and the project-scoped delegated user identity action required by the Responses endpoint.

The workflows configure the shared internal identity secret, but successful local signed
identity propagation does not prove that hosted delegated-user headers reach the agent.
Treat hosted identity transport as unverified until an end-to-end deployment test passes.
Toolbox and business-specific HITL policy also remain pending decisions; their settings
must not be read as evidence that either feature is active.

## Operational notes

- These workflows are intentionally independent by path filter to avoid unrelated deploys.
- If no files in a workflow path change, that workflow does not run on push.
- Manual runs are enabled for `cd-hosted-agent.yaml` and `cd-responses-bff.yaml` (`workflow_dispatch`).
- All workflows are non-interactive (`--no-prompt`) and fail fast when required values are missing.

## Data CI workflow details

`ci-data.yml` validates the Python data module under `app/business-api/data` without acting as a style gate.

- Blocking checks:
  - Dependency install (`uv sync --dev --frozen --no-build`)
  - Python syntax/bytecode compile check (`python -m compileall -q .`)
  - Tests (`pytest -q tests --junitxml=junit.xml`)
- Non-blocking signals:
  - Coverage summary (only when `coverage.xml` exists)
  - Test and coverage artifact upload (`junit.xml`, optional `coverage.xml`)
- Not included by design:
  - Strict lint/style gating (for example max line length)
  - SonarQube scan

## Troubleshooting

- If deployment fails with auth/authorization errors, verify OIDC federation and role assignments for the `Development` environment identity.
- If hosted-agent deployment fails early, verify the four required Foundry variables are set exactly as environment variables.
- If `azd` cannot resolve a service name, check that the command is using the correct `azure.yaml` root (`-C app/agent` for hosted agent).
