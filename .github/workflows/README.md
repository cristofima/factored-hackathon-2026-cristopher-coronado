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
| `ci-responses-bff.yml`  | Validate Responses BFF build/tests      | `app/responses-bff/**`                 | n/a              | Shared action (`ci-python`)                              |
| `ci-hosted-agent.yml`   | Validate hosted-agent build/tests       | `app/agent/**`                         | n/a              | Shared action (`ci-python`)                              |
| `ci-data.yml`           | Validate data module build/tests        | `app/business-api/data/**`             | n/a              | Shared action (`ci-python`)                              |
| `ci-frontend.yml`       | Validate frontend lint/tests/build      | `app/frontend/banking-web/**`          | n/a              | Shared action (`ci-node`)                                |
| `cd-account.yaml`       | Deploy Account API App Service          | `app/business-api/account/**`          | repository root  | `azd deploy account --no-prompt`                         |
| `cd-transaction.yaml`   | Deploy Transaction API App Service      | `app/business-api/transaction/**`      | repository root  | `azd deploy transaction --no-prompt`                     |
| `cd-responses-bff.yaml` | Deploy JWT-protected Responses BFF      | `app/responses-bff/**`                 | repository root  | `azd deploy responses-bff --no-prompt`                   |
| `cd-frontend.yaml`      | Deploy frontend Web App Service         | `app/frontend/banking-web/**`          | repository root  | `azd deploy web --no-prompt`                             |
| `cd-hosted-agent.yaml`  | Deploy Foundry hosted agent             | `app/agent/**` and `workflow_dispatch` | `app/agent`      | `azd -C app/agent deploy home-banking-agent --no-prompt` |

## Why two azd project roots exist

This repository uses two independent `azure.yaml` manifests:

1. Root [azure.yaml](../../azure.yaml): App Service stack (`account`, `transaction`, `responses-bff`, `web`).
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

### Shared secrets Key Vault (`cd-responses-bff.yaml`, `cd-account.yaml`, `cd-transaction.yaml`, `cd-hosted-agent.yaml`)

`JWT_SECRET_KEY` (the application JWT signing key, at least 32 characters) and
`INTERNAL_IDENTITY_SECRET` (the BFF-to-agent signed identity secret, at least 32
characters) live once in the shared Key Vault Terraform provisions
(`azurerm_key_vault.secrets` in `infra/main.tf`), not as GitHub Environment Secrets.

- Account, Transaction, and the Responses BFF App Services reference both secrets as
  `@Microsoft.KeyVault(SecretUri=...)` app settings, declared directly in `infra/main.tf`
  and resolved by each App Service's system-assigned managed identity (granted
  `Key Vault Secrets User` on the vault). No workflow writes these values anymore;
  `cd-account.yaml`/`cd-transaction.yaml`/`cd-responses-bff.yaml` only validate that
  `JWT_SECRET_KEY`/`INTERNAL_IDENTITY_SECRET` (plus `DATABASE_URL`/`CORS_ALLOWED_ORIGINS`
  for Account/Transaction) are already present on the target App Service before deploying,
  failing fast with an `azd provision` hint if Terraform hasn't run yet.
- Foundry hosted agents have no native Key Vault app-setting reference, so
  `cd-hosted-agent.yaml` resolves `internal-identity-secret` itself with
  `az keyvault secret show`, masks it with `::add-mask::`, and exports it through
  `$GITHUB_ENV` before passing it to `azd -C app/agent env set`.
- Set `AZURE_KEY_VAULT_NAME` under **Settings > Environments > Development > Variables**
  to the Key Vault name from Terraform's `AZURE_KEY_VAULT_NAME` output
  (`azd env get-value AZURE_KEY_VAULT_NAME`).
- The GitHub Actions federated identity needs `Key Vault Secrets User` on the vault to
  run the `cd-hosted-agent.yaml` resolve step; grant it via Terraform's
  `github_actions_principal_id` variable (the service principal's object ID, not its
  client/app ID) or with `az role assignment create` directly.
- Terraform never writes the secret _values_ themselves (`azurerm_key_vault_secret` is
  deliberately not used); they're uploaded once, by hand, with `az keyvault secret set`,
  so a raw value never enters `tfstate`.

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

### Frontend variables (`cd-frontend.yaml`)

Vite bakes `VITE_*` values into the bundle at build time, not at runtime, and `azd deploy web`
builds the bundle in the runner before upload. Two approaches were tried and don't work: Terraform
App Service application settings (the build never reads them, since the bundle is already built
before the zip reaches Azure; no such `VITE_*` app settings exist in `infra/main.tf` anymore) and a
root `azure.yaml` `postprovision` hook deriving them from Terraform outputs for local `azd deploy`
(removed, since this workflow is the only validated deploy path and never provisions). Set these
four directly under **Settings > Environments > Development > Variables**, using the deployed App
Service hostnames:

- `VITE_ACCOUNT_API_URL` (`https://<account-app-hostname>/api`)
- `VITE_TRANSACTION_API_URL` (`https://<transaction-app-hostname>/api`)
- `VITE_RESPONSES_BFF_URL` (`https://<responses-bff-app-hostname>`)
- `VITE_RESPONSES_API_URL` (`https://<responses-bff-app-hostname>/responses`)

The workflow validates and injects them with `azd env set` before `azd deploy web --no-prompt`,
the same pattern `cd-hosted-agent.yaml` uses for `ACCOUNT_MCP_URL`/`TRANSACTION_MCP_URL`. Update
these four if the backing App Services are ever recreated (their default hostnames include a
non-deterministic suffix). This relies on `azd` >=1.23.7, pinned in the root `azure.yaml`'s
`requiredVersions`: before that release, `azd env set` values reached Docker builds and hooks
only, never non-Docker framework subprocesses like `npm run build`
(see [Azure/azure-dev#6903](https://github.com/Azure/azure-dev/issues/6903)), so Vite would
silently build with blank values instead of failing.

A second, independent problem produced the same symptom (the login page kept pointing at
`http://localhost:8080`) even after the above was fixed: the `web` service's `azure.yaml` entry
had no `dist` property, so `azd deploy web` packaged the entire project (`package.json`, `src/`,
`.env.local`, the already-built `dist/`) instead of only the built output. Azure's Kudu pipeline
auto-detects `package.json` in that zip and runs its own remote Oryx build
(`SCM_DO_BUILD_DURING_DEPLOYMENT=true` + `POST_BUILD_COMMAND=npm run build`), which re-bakes
`VITE_*` from whatever `.env.local` is sitting in the uploaded source, with no overriding
Application Settings on the server, and silently overwrites azd's already-correct local/CI build.
Confirmed directly from the App Service's own deployment log: `Running oryx build...` followed by
`Deployment successful ... Remote build.`. Fixed by setting `dist: dist` on the `web` service in
the root `azure.yaml`, so azd deploys only the built `dist/` output, with no `package.json` for
Oryx to detect; `infra/main.tf` was updated to match (`appCommandLine` serves
`/home/site/wwwroot` directly instead of a nested `dist/` subfolder, and the now-dead
`SCM_DO_BUILD_DURING_DEPLOYMENT`/`POST_BUILD_COMMAND` settings were removed for `web`).

## Hosted-agent workflow details

`cd-hosted-agent.yaml` performs these steps:

1. Installs Foundry `azd` extension (`microsoft.foundry`) in the runner.
2. Authenticates with Azure via OIDC.
3. Resolves `internal-identity-secret` from the shared Key Vault and masks it.
4. Creates/selects `development` `azd` environment in `app/agent`.
5. Validates required Foundry variables before deployment.
6. Sets environment variables with `azd -C app/agent env set ...`.
7. Deploys only `home-banking-agent`.
8. Prints agent status with `azd -C app/agent ai agent show --no-prompt`.

## Responses BFF workflow details

`cd-responses-bff.yaml` performs these steps:

1. Authenticates with Azure via OIDC and selects the root `development` azd environment.
2. Validates that `JWT_SECRET_KEY`/`INTERNAL_IDENTITY_SECRET` are already present on the
   provisioned BFF App Service (Key Vault references set by Terraform) without printing them.
3. Deploys only `responses-bff`.

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
