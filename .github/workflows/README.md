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

| Workflow file           | Purpose                                                   | Trigger path                           | azd project root | Main command                                             |
| ----------------------- | --------------------------------------------------------- | -------------------------------------- | ---------------- | -------------------------------------------------------- |
| `ci-identity.yml`       | Validate Identity build/tests and deployment requirements | `app/business-api/identity/**`         | n/a              | Shared action (`ci-python`)                              |
| `cd-identity.yaml`      | Test and deploy existing Identity App Service             | `app/business-api/identity/**`         | repository root  | `azd deploy identity --no-prompt`                        |
| `ci-account.yml`        | Validate Account API Python build/tests                   | `app/business-api/account/**`          | n/a              | Shared action (`ci-python`)                              |
| `ci-transaction.yml`    | Validate Transaction API build/tests                      | `app/business-api/transaction/**`      | n/a              | Shared action (`ci-python`)                              |
| `ci-responses-bff.yml`  | Validate Responses BFF build/tests                        | `app/responses-bff/**`                 | n/a              | Shared action (`ci-python`)                              |
| `ci-hosted-agent.yml`   | Validate hosted-agent build/tests                         | `app/agent/**`                         | n/a              | Shared action (`ci-python`)                              |
| `ci-data.yml`           | Validate data module build/tests                          | `app/business-api/data/**`             | n/a              | Shared action (`ci-python`)                              |
| `ci-frontend.yml`       | Validate frontend lint/tests/build                        | `app/frontend/banking-web/**`          | n/a              | Shared action (`ci-node`)                                |
| `cd-account.yaml`       | Deploy Account API App Service                            | `app/business-api/account/**`          | repository root  | `azd deploy account --no-prompt`                         |
| `cd-transaction.yaml`   | Deploy Transaction API App Service                        | `app/business-api/transaction/**`      | repository root  | `azd deploy transaction --no-prompt`                     |
| `cd-responses-bff.yaml` | Deploy JWT-protected Responses BFF                        | `app/responses-bff/**`                 | repository root  | `azd deploy responses-bff --no-prompt`                   |
| `cd-frontend.yaml`      | Deploy frontend Web App Service                           | `app/frontend/banking-web/**`          | repository root  | `azd deploy web --no-prompt`                             |
| `cd-hosted-agent.yaml`  | Deploy Foundry hosted agent                               | `app/agent/**` and `workflow_dispatch` | `app/agent`      | `azd -C app/agent deploy home-banking-agent --no-prompt` |

## Replay smoke on PRs

[ci-hosted-agent.yml](ci-hosted-agent.yml) also validates replay harness changes
and Account/Transaction MCP tool contracts. After offline tests, same-repository
PRs run the three synthetic cases with a real model using `azure/login@v2`, OIDC,
and the `Development` environment. Required variables are `AZURE_CLIENT_ID`,
`AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `FOUNDRY_PROJECT_ENDPOINT`, and
`MODEL_DEPLOYMENT_NAME`. The federated identity must be authorized to call the
model. No Key Vault secret resolution, deployment, or provisioning is performed.

Missing configuration or incomplete/failed evidence fails the smoke job. A sticky
comment and job summary show protocol statuses; full synthetic evidence remains
in 14-day artifacts. Fork PRs only receive a non-execution notice. This job is not
a dispute quality or real authorization gate. Actual PR execution, OIDC access,
and required-check settings are unverified. See the [evaluation guide](../../evals/README.md#pr-smoke-check).

## Why two azd project roots exist

This repository uses two independent `azure.yaml` manifests:

1. Root [azure.yaml](../../azure.yaml): App Service deployments (`identity`, `account`, `transaction`, `responses-bff`, `web`), provisioned through root Terraform. Each CD workflow requires its explicit App Service name variable, exported into azd and bound by the manifest’s `resourceName`. Python preflight looks up that exact name; tags do not select deployment targets.
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

Root CD also requires a GitHub `Development` variable whose value matches its
service’s Terraform name output. Terraform outputs, azd variables, root manifest
bindings and GitHub Variables all use the same `_APP_NAME` names:

| Service       | Required GitHub variable       | Terraform output / azd variable |
| ------------- | ------------------------------ | ------------------------------- |
| Identity      | `AZURE_IDENTITY_APP_NAME`      | `AZURE_IDENTITY_APP_NAME`       |
| Account       | `AZURE_ACCOUNT_APP_NAME`       | `AZURE_ACCOUNT_APP_NAME`        |
| Transaction   | `AZURE_TRANSACTION_APP_NAME`   | `AZURE_TRANSACTION_APP_NAME`    |
| Responses BFF | `AZURE_RESPONSES_BFF_APP_NAME` | `AZURE_RESPONSES_BFF_APP_NAME`  |
| Web           | `AZURE_WEB_APP_NAME`           | `AZURE_WEB_APP_NAME`            |

Shared Azure setup validates the GitHub value and exports it under the same
azd variable with `azd env set`. Terraform outputs are not automatically published
to GitHub Variables.
Missing/invalid names fail before authentication. The separate Foundry agent
project omits both App Service name inputs.

### Shared secrets Key Vault (`cd-responses-bff.yaml`, `cd-account.yaml`, `cd-transaction.yaml`, `cd-hosted-agent.yaml`)

`JWT_SECRET_KEY` (application JWT), `AUTH_INTERNAL_SECRET` (Identity introspection),
and `INTERNAL_IDENTITY_SECRET` (agent transport) are distinct secrets, each at least
32 characters, stored in the shared Key Vault Terraform provisions
(`azurerm_key_vault.secrets` in `infra/main.tf`), not as GitHub Environment Secrets.
Preflights inspect reference syntax and App Service `Resolved` metadata only;
they never retrieve resolved secret values or prove their length.

- Python App Services use versionless `@Microsoft.KeyVault(SecretUri=...)` references,
  resolved by their system-assigned managed identities (`Key Vault Secrets User`).
  The shared `appservice-preflight` action requires `Resolved` reference status for
  JWT/introspection secrets and database URLs; consumers also require the agent
  transport secret. Account/Transaction require `CORS_ALLOWED_ORIGINS`.
- Consumers require remote HTTPS `AUTH_USERS_ENDPOINT` without loopback/IP literals,
  credentials, query or fragment, and explicit nonempty `JWT_ISSUER`/`JWT_AUDIENCE`.
  The DB-free Responses BFF rejects any `DATABASE_URL` app setting, including an empty one.
  These are configuration gates, not connectivity, login or matching-secret evidence.
  OIDC needs App Service configuration/reference-metadata read and deployment permissions,
  not permission to retrieve vault values for these preflights.
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
- Authentication secret values are supplied separately, not managed as Terraform
  secret resources. Terraform does manage `database-url` using its generated
  PostgreSQL administrator credential, shared by Identity, Account and Transaction.
  That URL/password enters sensitive Terraform state; restrict backend and saved-plan
  access. Sensitive marking does not remove values from state.

### Identity deployment (`cd-identity.yaml`)

Identity uses the five shared Azure variables plus `AZURE_IDENTITY_APP_NAME` in
`Development`, like the other App Service workflows. Root azd deployment
and preflight target that exact physical name. The OIDC identity needs
permission to read app configuration and deploy that app. No Identity passwords or
JWT/introspection secrets belong in GitHub variables or workflow logs.

Identity CI uses Python 3.11, synthetic pytest tests and JUnit artifacts. Both CI and
CD opt into the shared `ci-python` action's `deployment-requirements: requirements.txt`
check to run `uv pip compile` against `pyproject.toml`
for Linux (`x86_64-unknown-linux-gnu`), Python 3.11, excluding `banking-shared`.
The artifact generator uses:

```bash
uv pip compile app/business-api/identity/pyproject.toml --no-emit-package banking-shared --python-version 3.11 --python-platform x86_64-unknown-linux-gnu -o app/business-api/identity/requirements.txt
```

Existing `requirements.txt` pins constrain recompilation to avoid upstream version drift;
comparison ignores comments/blank lines and rejects local/editable package paths.
The App Service action also runs synthetic configuration/target-selection regressions
(`node --test .github/actions/appservice-preflight/preflight.test.cjs`) before preflight.
The frozen lockfile still governs CI installation/tests, not the Oryx runtime artifact.
CD repeats checks before Azure authentication; manual Identity deployments are restricted
to `main`. Deployments are serialized and never cancel an in-progress deployment.

Provision the root Terraform stack and configure approved secrets before running CD.
Preflight requires the existing app named by `AZURE_IDENTITY_APP_NAME` in
`AZURE_RESOURCE_GROUP`, independently of tags. Required
App Service configuration:

- Linux runtime `PYTHON|3.11`.
- Startup command `python -m uvicorn identity.main:create_app --factory --host 0.0.0.0 --port 8000`.
- Nonempty `DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_ISSUER`, `JWT_AUDIENCE`, and
  `AUTH_INTERNAL_SECRET`; database/JWT/introspection settings must be versionless
  Key Vault references with `Resolved` metadata, and issuer/audience explicit values.
- `SCM_DO_BUILD_DURING_DEPLOYMENT=true` for Oryx dependency installation.
- Optional `ACCESS_TOKEN_MINUTES` (default 15, valid range 1–60).

Use approved secret storage/Key Vault references and database network/grant configuration.
`AUTH_INTERNAL_SECRET` is the shared introspection secret, not the agent transport
secret `INTERNAL_IDENTITY_SECRET`. Configure BFF, Account and Transaction with the
Identity URL in `AUTH_USERS_ENDPOINT` and matching JWT/introspection settings through
root Terraform. Rollout remains gated: provision/configure references, deploy Identity,
perform separately approved Identity acceptance checks, then deploy consumers. Independent
workflows do not enforce cross-workflow ordering or prove acceptance.

CD does not probe `/openapi.json`; endpoint exposure and a safe readiness contract
are deferred. Configuration preflight checks reference metadata before deployment,
not secret contents, startup, PostgreSQL connectivity, login or end-to-end authorization.
CI/CD never applies migrations, seeds users, bootstraps administrators or provisions
infrastructure. See the [Identity guide](../../app/business-api/identity/README.md#cicd).

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

Optional (per-agent model deployments):

- `TRIAGE_MODEL_DEPLOYMENT_NAME`
- `ACCOUNT_MODEL_DEPLOYMENT_NAME`
- `TRANSACTION_MODEL_DEPLOYMENT_NAME`

The workflow forwards these existing GitHub Environment variables with
`azd -C app/agent env set`, including empty values when unset. They are not part of
its required-variable validation; `MODEL_DEPLOYMENT_NAME` remains required.

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
2. Looks up the explicitly named app and validates resolved JWT/introspection/agent
   Key Vault references, explicit issuer/audience, a remote HTTPS Identity endpoint,
   and absence of `DATABASE_URL`, without printing setting values.
3. Deploys only `responses-bff`.

The BFF App Service uses its system-assigned managed identity to call Foundry. Terraform grants that identity the built-in `Foundry Agent Consumer` role and the project-scoped delegated user identity action required by the Responses endpoint.

Terraform configures the shared agent-transport secret, and consumer deployment preflights
check its Key Vault reference metadata; successful local signed identity propagation does
not prove that hosted delegated-user headers reach the agent.
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
