# CI/CD Workflows

This directory contains the GitHub Actions workflows used to deploy application services after infrastructure has already been provisioned manually.

## Deployment model

- Target branch: `main`
- Target GitHub Environment: `Development`
- Authentication: GitHub OIDC with `azure/login@v2`
- Provisioning in CI: not allowed (`azd provision` is intentionally not used here)
- Deploy command pattern: `azd deploy <service> --no-prompt`

## Workflow inventory

| Workflow file              | Purpose                            | Trigger path                             | azd project root | Deploy command                                             |
| -------------------------- | ---------------------------------- | ---------------------------------------- | ---------------- | ---------------------------------------------------------- |
| `deploy-account.yaml`      | Deploy Account API App Service     | `app/business-api/account/**`            | repository root  | `azd deploy account --no-prompt`                           |
| `deploy-payment.yaml`      | Deploy Payment API App Service     | `app/business-api/payment/**`            | repository root  | `azd deploy payment --no-prompt`                           |
| `deploy-transaction.yaml`  | Deploy Transaction API App Service | `app/business-api/transaction/**`        | repository root  | `azd deploy transaction --no-prompt`                       |
| `deploy-web.yaml`          | Deploy frontend Web App Service    | `app/frontend/banking-web/**`            | repository root  | `azd deploy web --no-prompt`                               |
| `deploy-hosted-agent.yaml` | Deploy Foundry hosted agent        | `app/backend/**` and `workflow_dispatch` | `app/backend`    | `azd -C app/backend deploy home-banking-agent --no-prompt` |

## Why two azd project roots exist

This repository uses two independent `azure.yaml` manifests:

1. Root [azure.yaml](../../azure.yaml): App Service stack (`account`, `payment`, `transaction`, `web`).
2. Backend [azure.yaml](../../app/backend/azure.yaml): Foundry hosted-agent stack (`home-banking-agent`).

For that reason, `deploy-hosted-agent.yaml` always uses `azd -C app/backend ...` so it resolves the backend manifest explicitly and never the root manifest.

## Required GitHub Environment variables

Set these in **Settings > Environments > Development > Variables**.

### Shared variables (all workflows)

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_LOCATION`

### Hosted-agent variables (deploy-hosted-agent.yaml)

Required:

- `FOUNDRY_PROJECT_ENDPOINT`
- `AZURE_AI_PROJECT_ID`
- `MODEL_DEPLOYMENT_NAME`
- `TOOLBOX_ENDPOINT`

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

## Operational notes

- These workflows are intentionally independent by path filter to avoid unrelated deploys.
- If no files in a workflow path change, that workflow does not run on push.
- Manual runs are currently enabled only for `deploy-hosted-agent.yaml` (`workflow_dispatch`).
- All workflows are non-interactive (`--no-prompt`) and fail fast when required values are missing.

## Troubleshooting

- If deployment fails with auth/authorization errors, verify OIDC federation and role assignments for the `Development` environment identity.
- If hosted-agent deployment fails early, verify the four required Foundry variables are set exactly as environment variables.
- If `azd` cannot resolve a service name, check that the command is using the correct `azure.yaml` root (`-C app/backend` for hosted agent).
