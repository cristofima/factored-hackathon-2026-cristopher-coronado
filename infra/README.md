# Terraform provisioning

The root `azure.yaml` runs `azd provision` against this directory and `azd deploy` for five Linux App Services: Identity, Account, Transaction, the Responses BFF, and the web frontend. The hosted agent has its own `app/agent/azure.yaml` and is not an App Service or a Terraform resource in this stack. Terraform uses an existing resource group and provisions one shared Linux plan, five web sites, Log Analytics, Application Insights, Blob storage, PostgreSQL, and a dedicated Foundry account and project. The separate Foundry azd project deploys the hosted agent; it consumes the project endpoint provisioned here.

The BFF binds its opaque conversation tokens to the authenticated user, but only forwards them upstream in local mode. Hosted mode does not yet link turns using platform conversation IDs or `previous_response_id`; see the [BFF conversation guide](../app/responses-bff/README.md#validation-and-limits). Before production use, verify the hosted agent and BFF identities have only the required Foundry permissions. Do not import role assignments targeting the removed legacy backend App Service identity for a different principal. Blob storage is still provisioned for existing business-service compatibility and remains publicly reachable unless a private endpoint or VNet path is designed separately.

## Prerequisites

Select a single subscription, resource group, and azd environment. The resource group and the remote-state storage account/container must already exist before the first provision; do not put application data in the state container. Grant the Terraform identity Storage Blob Data Contributor on the state container and appropriate permissions to provision resources in the resource group. Authenticate with Azure CLI as well as azd (`azd config set auth.useAzCliAuth true`), then set these azd values: `AZURE_SUBSCRIPTION_ID`, `AZURE_LOCATION`, `AZURE_RESOURCE_GROUP`, `RS_STORAGE_ACCOUNT`, and `RS_CONTAINER_NAME`. `AZURE_ENV_NAME` comes from the selected azd environment. Keep the state storage in the selected resource group. The remote state key is `banking-assistant.tfstate`; use one state for the one environment. The Terraform state backend uses Microsoft Entra authentication and Azure Blob lease locking.

The root Terraform files use `main.tfvars.json` for azd interpolation and `provider.conf.json` for remote state; do not put credentials in either file. For direct Terraform commands, pass equivalent variables in an untracked `.tfvars` file and initialize with `-backend-config` using real state account/container values instead of the `${...}` azd placeholders. Never commit state, plans, or secret values. The checked-in lock file pins resolved provider versions. The new Foundry account is created with system-assigned identity and project management enabled from its first request; the project-management setting cannot be enabled retroactively on an existing account.

## Existing resources

The checked-in `main.tfvars.json` sets `postgres_location = "centralus"` because
the East US 2 PostgreSQL capacity request was denied, and this provisioning path was
validated successfully in Central US. Only PostgreSQL uses this override; App
Services, storage, monitoring, and Foundry retain the existing resource group region.
A null or omitted override uses the resource group region. Direct Terraform runs must
also pass `postgres_location = "centralus"` in their local variable file.

PostgreSQL server and database names are resolved from azd environment variables in
`main.tfvars.json` (`${POSTGRES_SERVER_NAME}` and `${POSTGRES_DATABASE_NAME}`) rather
than hardcoded values. The current low-cost baseline is Burstable
`B_Standard_B1ms` with `postgres_storage_mb = 32768` (32 GiB), which is the minimum
supported storage size returned by the Central US Burstable SKU catalog for this
subscription at provisioning time. If latency or throughput becomes a bottleneck,
increase `postgres_sku_name` (for example to `B_Standard_B2s` or `B_Standard_B2ms`)
and reprovision.

Cross-region database access adds latency and may incur data-transfer charges.
Catalog support and `terraform validate` do not guarantee capacity at creation time.
Changing the region of an existing server requires replacement and a separate data
migration.

PostgreSQL Flexible Server has `publicNetworkAccess = "Enabled"`, but the only firewall
rule created by default (`AllowAllAzureServicesAndResourcesWithinAzureIps`, the special
`0.0.0.0`/`0.0.0.0` range) permits Azure-hosted resources only, not an arbitrary public
IP. To reach the server directly from a local client such as pgAdmin, set the azd
environment value `POSTGRES_ALLOWED_CLIENT_IP` to that single public IP
(`azd env set POSTGRES_ALLOWED_CLIENT_IP <your-ip>`) before provisioning; `main.tfvars.json`
forwards it to `postgres_allowed_client_ip`, which creates one extra `AllowLocalClientIp`
firewall rule. Leave the value unset to keep the server reachable only from Azure. Rotate
or remove this value (and reprovision) whenever the allowed IP changes.

Before enabling `azd provision` against an existing Bicep deployment, inspect the actual resource IDs and names. Set `app_names` and the storage name override for existing resources; set `hostname_scope = null` when importing sites created without a unique hostname. Azure only accepts the unique hostname scope on site creation; changing it on an existing site requires replacing that site. Back up the existing deployment and Terraform state before any cutover. Import each managed resource (the plan, existing sites, monitoring, storage account, and container) with `terraform import -var-file=<local.tfvars> <address> <resource-id>` after initializing remote state. Example Terraform addresses: `azurerm_service_plan.main`, `azapi_resource.app["account"]`, `azurerm_log_analytics_workspace.main`, `azurerm_application_insights.main`, `azurerm_storage_account.content`, and `azurerm_storage_container.content`. The Responses BFF is a new dedicated resource at `azapi_resource.responses_bff`; do not import an unrelated backend site at that address. Terraform does not automatically import Bicep-managed resources. Review `terraform plan` for **zero unexpected deletes or replacements** before running `azd provision`. Do not run Bicep and Terraform provisioning concurrently on the same resources.

The app names, derived web URLs, and infrastructure settings are emitted as Terraform outputs for azd. Do not derive a web URL from the site name when unique hostnames are enabled; consume the `defaultHostName` output. The root environment also receives `AZURE_OPENAI_ENDPOINT`, `FOUNDRY_PROJECT_ENDPOINT`, `AZURE_RESPONSES_BFF_APP_NAME`, `RESPONSES_BFF_URI`, `AZURE_IDENTITY_APP_NAME`, and `IDENTITY_URI`. Root azd binds every service through `resourceName` to its corresponding `_APP_NAME` Terraform output. Standalone CD exports that same name into its azd environment; tags remain metadata, not deployment selectors. Identity uses dedicated address `azapi_resource.identity` and defaults to `app-identity-<environment>`; adopt/import an existing site deliberately before provisioning. `azd deploy --cwd app/agent` is the separate hosted-agent deploy path; plain root `azd deploy` targets only the five App Services.

Terraform deliberately does **not** set `VITE_*` App Service application settings for the
web frontend: Vite bakes those values into the bundle at build time, before `azd deploy web`
ever uploads it, so settings applied to the running App Service can never reach the already-built
bundle. `.github/workflows/cd-frontend.yaml` injects `VITE_ACCOUNT_API_URL`,
`VITE_TRANSACTION_API_URL`, `VITE_RESPONSES_BFF_URL`, and `VITE_RESPONSES_API_URL` with
`azd env set` immediately before that build step instead; see
[../.github/workflows/README.md](../.github/workflows/README.md#frontend-variables-cd-frontendyaml).

Terraform provisions a shared RBAC-authorized, purge-protected Key Vault and uses
versionless `@Microsoft.KeyVault(SecretUri=...)` app settings. System-assigned
identities receive `Key Vault Secrets User` at individual secret scopes:

| Service               | Permitted secrets                                                                    |
| --------------------- | ------------------------------------------------------------------------------------ |
| Identity              | `database-url`, `jwt-secret-key`, `auth-internal-secret`                             |
| Account / Transaction | `database-url`, `jwt-secret-key`, `auth-internal-secret`, `internal-identity-secret` |
| Responses BFF         | `jwt-secret-key`, `auth-internal-secret`, `internal-identity-secret`                 |

Supply the three authentication secrets through approved private secret-entry
operations, never command arguments, source, logs or Terraform secret-value data sources.
Identity reuses the same Terraform-managed `database-url` reference as Account and
Transaction; no second database secret or credential copy is required. Neither this
infrastructure nor deployment bootstraps users or runs migrations. Identity does not
consume the agent-only `internal-identity-secret`.

Terraform manages `database-url` for Identity, Account and Transaction using the PostgreSQL
administrator credential. Sharing that administrator principal is an explicitly approved
prototype tradeoff, not least-privilege database isolation. That URL/password resides in sensitive state; restrict backend
and saved-plan access. Sensitive marking does not remove data from state. The BFF has no
`DATABASE_URL` or database-secret assignment. Applying this change replaces existing
vault-wide consumer grants with secret-scoped grants; inspect the approved preview for
unexpected changes and audit inherited/manual RBAC and PostgreSQL grants separately.
These declarations alone do not prove deployed isolation or least-privilege DB access.

All three consumers receive HTTPS `AUTH_USERS_ENDPOINT` from Identity's actual hostname
and the same explicit `JWT_ISSUER`/`JWT_AUDIENCE` (defaults `home-banking-api` and
`home-banking-web`), JWT key and introspection secret. Identity's
`ACCESS_TOKEN_MINUTES` defaults to 15 and must be an integer from 1–60. JWT and
introspection secrets must each satisfy the runtime's 32-character minimum. Account
and Transaction continue verifying browser JWTs independently of agent-only transport. Terraform sets
`CORS_ALLOWED_ORIGINS` for Account and Transaction to the deployed web app's origin
directly (no secret involved). Native App Service CORS is explicitly cleared on Account,
Transaction, and the BFF; their Python `CORSMiddleware` implementations are the sole CORS
owners. The BFF receives its allowed web origin through `ALLOWED_ORIGINS`.
Foundry hosted agents have no native Key Vault app-setting reference, so
`cd-hosted-agent.yaml` resolves `internal-identity-secret` itself with `az keyvault secret
show` before passing it to `azd -C app/agent env set`; see
[../.github/workflows/README.md](../.github/workflows/README.md). The BFF identity
receives `Foundry Agent Consumer` and a custom project-scoped role containing
`Microsoft.CognitiveServices/accounts/agents/UserIdentityImpersonation/action`. Do not send
Azure credentials or the delegated identity header from the browser.

Terraform owns the complete app settings arrays through `azapi_resource.app`,
`azapi_resource.identity`, and `azapi_resource.responses_bff`. There is no separate `api_cors` patch resource or
`ignore_changes` rule for these arrays. Provisioning applies settings to both new and
existing sites; declare persistent changes in Terraform rather than patching settings
manually, because a later provision can overwrite those manual changes.

Account starts with `python -m uvicorn banking_account.main:app --host 0.0.0.0 --port 8080 --proxy-headers`;
Transaction uses `banking_transaction.main:app` with the same options.
Uvicorn reads `FORWARDED_ALLOW_IPS=*` from the App Service environment
to trust the forwarded HTTPS scheme. Keeping the wildcard out of the startup command
avoids shell expansion by Oryx. This trust setting is scoped to the controlled App Service
proxy environment. These commands import the qualified package's `main:app`; they do not execute the
`if __name__ == "__main__"` block used by `python -m banking_account.main`
or `python -m banking_transaction.main` locally.

Changes to these startup commands or app settings require provisioning, not a service
code deploy. Code or dependency changes still require deployment. After provisioning,
verify service startup, HTTPS redirects, and browser CORS preflight responses; successful
Terraform validation alone does not prove runtime health.

By convention in this repository, the frontend App Service name is `app-banking-web-<env>` (for example, `app-banking-web-development`). Keep this explicit naming when adding environments so the web workload is distinguishable from account/transaction services.

Identity starts with `python -m uvicorn identity.main:create_app --factory --host 0.0.0.0 --port 8000`
on Python 3.11 with Oryx enabled. Apply forward Identity migrations through the approved
head with a separate authorized principal before admitting traffic; never migrate at
startup. Provisioning changes consumers' settings, so use an approved maintenance window:
preview first, migrate, provision, deploy Identity, verify resolved references and bounded
DB/schema readiness, then deploy compatible consumers and require fresh login. CD does
not probe OpenAPI; endpoint exposure and a readiness contract are deferred. Metadata
preflight and deployment success do not prove startup, database access or login.

All root services deploy by explicit App Service name in the configured resource
group. Set GitHub `Development` Variables manually from the identically named
Terraform outputs: `AZURE_IDENTITY_APP_NAME`, `AZURE_ACCOUNT_APP_NAME`,
`AZURE_TRANSACTION_APP_NAME`, `AZURE_RESPONSES_BFF_APP_NAME`, and
`AZURE_WEB_APP_NAME`. Terraform does not publish these GitHub Variables automatically.
The root manifest uses those same `_APP_NAME` azd variables in `resourceName`;
shared CD validates each GitHub value and exports it under that same name before
deployment. Python-service preflight reads that exact app with `az webapp show`,
never tag-based discovery.

The existing secret-scoped Identity `database-url` grant is reconciled with
`azurerm_role_assignment.identity_key_vault_secrets_user["database-url"]` in the
approved remote Terraform state. Its targeted plan reported no changes, and the
subsequent `azd provision` was confirmed successful. If provisioning reports
`409 RoleAssignmentExists` for a pre-existing grant, verify its principal, role and
secret scope, then import its full role-assignment resource ID at the matching
Terraform address in the correct backend and workspace. Review the plan before
provisioning; do not delete or recreate the existing permission to resolve a state
mismatch. Resolved references and successful provisioning do not prove runtime readiness.

Retain compatible artifacts/configuration references before rollout. Rollback must preserve
the forward schema, current JWT contracts and introspection; never restore BFF database
access or bypass Identity. If Identity is unavailable, keep consumers fail-closed and repair
it. A database restore or schema downgrade requires separate approval.

## Checks

Run `terraform fmt -check -recursive` and `terraform validate` after initializing the providers. `terraform plan` and `azd provision` require Azure credentials, a pre-created backend, and the selected subscription; validation alone does not create or import any Azure resources. `azd deploy` requires successfully provisioned App Services and a working zip/build pipeline for the frontend and each service. Do not run `azd down` on the existing resource group as a rollback strategy.

Sources: [azd Terraform setup](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/use-terraform-for-azd) and [Azure App Service unique default hostnames](https://techcommunity.microsoft.com/blog/appsonazureblog/public-preview-creating-web-app-with-a-unique-default-hostname/4156353).
