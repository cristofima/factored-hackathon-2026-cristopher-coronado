# CI/CD Workflows

This directory contains the GitHub Actions workflows used to deploy application services after infrastructure has already been provisioned manually.

## Deployment model

- Target branch: `main`
- Target GitHub Environment: `Development`
- Authentication: GitHub OIDC with `azure/login@v2`
- Provisioning in CI: not allowed (`azd provision` is intentionally not used here)
- Deploy command pattern: `azd deploy <service> --no-prompt`

## Workflow inventory

| Workflow file               | Purpose                              | Trigger path                             | azd project root | Deploy command                                             |
| --------------------------- | ------------------------------------ | ---------------------------------------- | ---------------- | ---------------------------------------------------------- |
| `data-ci.yml`               | Validate Data Python build and tests | `app/business-api/data/**`               | n/a              | n/a                                                        |
| `deploy-account.yaml`       | Deploy Account API App Service       | `app/business-api/account/**`            | repository root  | `azd deploy account --no-prompt`                           |
| `deploy-payment.yaml`       | Deploy Payment API App Service       | `app/business-api/payment/**`            | repository root  | `azd deploy payment --no-prompt`                           |
| `deploy-transaction.yaml`   | Deploy Transaction API App Service   | `app/business-api/transaction/**`        | repository root  | `azd deploy transaction --no-prompt`                       |
| `deploy-responses-bff.yaml` | Deploy JWT-protected Responses BFF   | `app/responses-bff/**`                   | repository root  | `azd deploy responses-bff --no-prompt`                     |
| `deploy-web.yaml`           | Deploy frontend Web App Service      | `app/frontend/banking-web/**`            | repository root  | `azd deploy web --no-prompt`                               |
| `deploy-hosted-agent.yaml`  | Deploy Foundry hosted agent          | `app/backend/**` and `workflow_dispatch` | `app/backend`    | `azd -C app/backend deploy home-banking-agent --no-prompt` |

## Why two azd project roots exist

This repository uses two independent `azure.yaml` manifests:

1. Root [azure.yaml](../../azure.yaml): App Service stack (`account`, `payment`, `transaction`, `responses-bff`, `web`).
2. Backend [azure.yaml](../../app/backend/azure.yaml): Foundry hosted-agent stack (`home-banking-agent`).

For that reason, `deploy-hosted-agent.yaml` always uses `azd -C app/backend ...` so it resolves the backend manifest explicitly and never the root manifest.

## Required GitHub Environment variables

Set these in **Settings > Environments > Development > Variables**.

### Shared variables (all workflows)

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_LOCATION`
- `AZURE_RESOURCE_GROUP`

### Responses BFF secret (deploy-responses-bff.yaml)

Set `RESPONSES_BFF_JWT_SECRET` and `RESPONSES_BFF_AUTH_USERS` under **Settings > Environments > Development > Secrets**. The JWT secret must contain at least 32 characters. `RESPONSES_BFF_AUTH_USERS` is a JSON array of `id`, `customer_id`, `email`, `password_hash`, and `locale` fields; each password hash must be Argon2. The workflow writes both values directly to App Service settings, so Terraform and `azd` environment state never contain them.

### Internal identity secret

Set `INTERNAL_IDENTITY_SECRET` under **Settings > Environments > Development > Secrets**. Use the same value, with at least 32 characters, for the BFF, hosted agent, Account API, and Transaction API workflows. Each workflow injects it into its deployment target without printing it. Terraform intentionally does not manage this value, so it cannot enter Terraform state.

### Hosted-agent variables (deploy-hosted-agent.yaml)

Required:

- `FOUNDRY_PROJECT_ENDPOINT`
- `AZURE_AI_PROJECT_ID`
- `MODEL_DEPLOYMENT_NAME`

Optional (observability and tracing behavior):

- `ENABLE_INSTRUMENTATION`
- `ENABLE_SENSITIVE_DATA`
- `AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING`
- `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`

## Hosted-agent workflow details

`deploy-hosted-agent.yaml` performs these steps:

1. Installs Foundry `azd` extension (`microsoft.foundry`) in the runner.
2. Authenticates with Azure via OIDC.
3. Creates/selects `development` `azd` environment in `app/backend`.
4. Validates required Foundry variables before deployment.
5. Sets environment variables with `azd -C app/backend env set ...`.
6. Deploys only `home-banking-agent`.
7. Prints agent status with `azd -C app/backend ai agent show --no-prompt`.

## Responses BFF workflow details

`deploy-responses-bff.yaml` performs these steps:

1. Authenticates with Azure via OIDC and selects the root `development` azd environment.
2. Validates `RESPONSES_BFF_JWT_SECRET` and `RESPONSES_BFF_AUTH_USERS` without printing them.
3. Writes `JWT_SECRET_KEY` and `AUTH_USERS` directly to the provisioned BFF App Service.
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
- Manual runs are enabled for `deploy-hosted-agent.yaml` and `deploy-responses-bff.yaml` (`workflow_dispatch`).
- All workflows are non-interactive (`--no-prompt`) and fail fast when required values are missing.

## Data CI workflow details

`data-ci.yml` validates the Python data module under `app/business-api/data` without acting as a style gate.

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
- If `azd` cannot resolve a service name, check that the command is using the correct `azure.yaml` root (`-C app/backend` for hosted agent).
