# Terraform provisioning

The root `azure.yaml` runs `azd provision` against this directory and `azd deploy` for four Linux App Services: account, transaction, the Responses BFF, and the web frontend. The hosted agent has its own `app/agent/azure.yaml` and is not an App Service or a Terraform resource in this stack. Terraform uses an existing resource group and provisions one shared Linux plan, four web sites, Log Analytics, Application Insights, Blob storage, PostgreSQL, and a dedicated Foundry account and project. The separate Foundry azd project deploys the hosted agent; it consumes the project endpoint provisioned here.

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

The app names, derived web URLs, and infrastructure settings are emitted as Terraform outputs for azd. Do not derive a web URL from the site name when unique hostnames are enabled; consume the `defaultHostName` output. The root environment also receives `AZURE_OPENAI_ENDPOINT`, `FOUNDRY_PROJECT_ENDPOINT`, `AZURE_RESPONSES_BFF_NAME`, and `RESPONSES_BFF_URI`. `azd deploy --cwd app/agent` is the separate hosted-agent deploy path; plain root `azd deploy` targets only the four App Services.

Terraform deliberately does **not** set `VITE_*` App Service application settings for the
web frontend: Vite bakes those values into the bundle at build time, before `azd deploy web`
ever uploads it, so settings applied to the running App Service can never reach the already-built
bundle. `.github/workflows/cd-frontend.yaml` injects `VITE_ACCOUNT_API_URL`,
`VITE_TRANSACTION_API_URL`, `VITE_RESPONSES_BFF_URL`, and `VITE_RESPONSES_API_URL` with
`azd env set` immediately before that build step instead; see
[../.github/workflows/README.md](../.github/workflows/README.md#frontend-variables-cd-frontendyaml).

Terraform provisions a shared Key Vault (`azurerm_key_vault.secrets`, RBAC-authorized, purge
protection on) and configures `JWT_SECRET_KEY`/`INTERNAL_IDENTITY_SECRET` on the BFF,
Account, and Transaction App Services as `@Microsoft.KeyVault(SecretUri=...)` app setting
references, resolved by each service's system-assigned managed identity (granted
`Key Vault Secrets User` on the vault). Terraform does not manage the values of these
two identity secrets; upload each one exactly once, by hand,
with `az keyvault secret set --vault-name <AZURE_KEY_VAULT_NAME> --name jwt-secret-key --value <...>`
and the same for `internal-identity-secret`, so these raw identity secret values never enter `tfstate`.
Terraform does manage the `database-url` secret through
`azurerm_key_vault_secret.database_url`, and all three Python services consume it through
a `DATABASE_URL` Key Vault reference. Its connection string and the PostgreSQL admin
password are present in Terraform state; protect the remote state accordingly.
Account and Transaction verify that same
browser-issued JWT directly for their REST endpoints, so all three services resolve the
identical `JWT_SECRET_KEY` secret; keep it a single shared value. Terraform sets
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

Terraform owns the complete app settings arrays through `azapi_resource.app` and
`azapi_resource.responses_bff`. There is no separate `api_cors` patch resource or
`ignore_changes` rule for these arrays. Provisioning applies settings to both new and
existing sites; declare persistent changes in Terraform rather than patching settings
manually, because a later provision can overwrite those manual changes.

Account and Transaction start with `python -m uvicorn main:app --host 0.0.0.0 --port 8080 --proxy-headers`.
Uvicorn reads `FORWARDED_ALLOW_IPS=*` from the App Service environment
to trust the forwarded HTTPS scheme. Keeping the wildcard out of the startup command
avoids shell expansion by Oryx. This trust setting is scoped to the controlled App Service
proxy environment. The command imports `main:app`; it does not execute the
`if __name__ == "__main__"` block used by `python main.py` locally.

Changes to these startup commands or app settings require provisioning, not a service
code deploy. Code or dependency changes still require deployment. After provisioning,
verify service startup, HTTPS redirects, and browser CORS preflight responses; successful
Terraform validation alone does not prove runtime health.

By convention in this repository, the frontend App Service name is `app-banking-web-<env>` (for example, `app-banking-web-development`). Keep this explicit naming when adding environments so the web workload is distinguishable from account/transaction services.

## Checks

Run `terraform fmt -check -recursive` and `terraform validate` after initializing the providers. `terraform plan` and `azd provision` require Azure credentials, a pre-created backend, and the selected subscription; validation alone does not create or import any Azure resources. `azd deploy` requires successfully provisioned App Services and a working zip/build pipeline for the frontend and each service. Do not run `azd down` on the existing resource group as a rollback strategy.

Sources: [azd Terraform setup](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/use-terraform-for-azd) and [Azure App Service unique default hostnames](https://techcommunity.microsoft.com/blog/appsonazureblog/public-preview-creating-web-app-with-a-unique-default-hostname/4156353).
