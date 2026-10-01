# 🛠️ Troubleshooting

When provisioning Azure resources with `azd`/Terraform, you may hit errors that stop or
delay deployment. This lists the ones relevant to this repository's actual stack
(Terraform, Azure App Service, Azure Database for PostgreSQL Flexible Server, Azure
Monitor, and a Foundry account/project) — not generic Azure error documentation for
services this repository does not provision (no Container Apps, Azure Container
Registry, Cosmos DB, Key Vault, or Azure Search).

> [!NOTE]
> This repository has two azd project roots. In the command examples below, run `azd`
> from the repository root for the App Service stack (`./azure.yaml`), and use
> `--cwd app/agent` for hosted-agent operations (`./app/agent/azure.yaml`).

## ⚡ Most Frequently Encountered Errors

| Error Code                            | Common Cause                                    | Full Details                                            |
| ------------------------------------- | ----------------------------------------------- | ------------------------------------------------------- |
| **InsufficientQuota**                 | Not enough quota available in subscription      | [View Solution](#quota--capacity-limitations)           |
| **MissingSubscriptionRegistration**   | Required feature not registered in subscription | [View Solution](#subscription--access-issues)           |
| **ResourceGroupNotFound**             | RG doesn't exist or using old `.env` file       | [View Solution](#resource-group--deployment-management) |
| **DeploymentModelNotSupported**       | Foundry model not available in selected region  | [View Solution](#regional--location-issues)             |
| **ResourceNotFound**                  | Resource does not exist or cannot be found      | [View Solution](#resource-identification--references)   |
| **SpecialFeatureOrQuotaIdRequired**   | Subscription lacks access to a specific model   | [View Solution](#subscription--access-issues)           |
| **Conflict - No available instances** | App Service plan has insufficient capacity      | [View Solution](#quota--capacity-limitations)           |
| **AccountProvisioningStateInvalid**   | Resource used before provisioning completed     | [View Solution](#resource-state--provisioning)          |
| **RequestDisallowedByPolicy**         | Azure Policy blocking the requested operation   | [View Solution](#subscription--access-issues)           |

## 📖 Table of Contents

- [Subscription & Access Issues](#subscription--access-issues)
- [Quota & Capacity Limitations](#quota--capacity-limitations)
- [Regional & Location Issues](#regional--location-issues)
- [Resource Naming & Validation](#resource-naming--validation)
- [Resource Identification & References](#resource-identification--references)
- [Resource Group & Deployment Management](#resource-group--deployment-management)
- [Resource State & Provisioning](#resource-state--provisioning)

## Subscription & Access Issues

| Issue/Error Code                                                          | Description                                                        | Steps to Resolve                                                                                                                                                                                                                                                                          |
| ------------------------------------------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ReadOnlyDisabledSubscription**                                          | Subscription is disabled or in read-only state                     | Check if you have an active subscription before starting the deployment. Depending on the subscription type, it may need to be reactivated; see [Reactivate a disabled Azure subscription](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/subscription-disabled). |
| **Unauthorized - Operation cannot be completed without additional quota** | Insufficient quota for the requested operation                     | Check usage with `az vm list-usage --location "<Location>" -o table`; request more via [VM Quota Request](https://techcommunity.microsoft.com/blog/startupsatmicrosoftblog/how-to-increase-quota-for-specific-types-of-azure-virtual-machines/3792394).                                   |
| **CrossTenantDeploymentNotPermitted**                                     | Deployment across different Azure AD tenants not allowed           | Confirm your deployment identity and the target resource group are in the same tenant (`az account show`, `az group show --name <RG_NAME>`); for CI/CD, confirm the service principal belongs to the same tenant and has permissions on the resource group.                               |
| **RequestDisallowedByPolicy**                                             | Azure Policy blocking the requested operation                      | An Azure Policy is preventing the action; see [RequestDisallowedByPolicy](https://learn.microsoft.com/en-us/troubleshoot/azure/azure-kubernetes/create-upgrade-delete/error-code-requestdisallowedbypolicy).                                                                              |
| **SpecialFeatureOrQuotaIdRequired**                                       | Subscription lacks access to a specific Azure OpenAI/Foundry model | Submit a request via the [Azure OpenAI Model Access Request](https://customervoice.microsoft.com/Pages/ResponsePage.aspx?id=v4j5cvGGr0GRqy180BHbR7en2Ais5pxKtso_Pz4b1_xUQ1VGQUEzRlBIMVU2UFlHSFpSNkpOR0paRSQlQCN0PWcu) form for restricted models (for example `gpt-5`, `o3`).             |
| **ResourceProviderError**                                                 | Resource provider not registered in subscription                   | Register it; see [Register Resource Provider](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-register-resource-provider?tabs=azure-cli).                                                                                                            |

## Quota & Capacity Limitations

| Issue/Error Code                                              | Description                                               | Steps to Resolve                                                                                                                                                                                                                                                                         |
| ------------------------------------------------------------- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **InsufficientQuota**                                         | Not enough quota available in the subscription            | Check quota with `Get-AzVMUsage -Location "<region>"` (PowerShell) or `az vm list-usage`, then request more if needed.                                                                                                                                                                   |
| **Conflict - No available instances to satisfy this request** | Azure App Service has insufficient capacity in the region | Wait and retry `azd up` after 15-30 minutes, deploy to a different region (set `AZURE_LOCATION` and re-run `azd env new`/`azd up`), or move to a higher App Service SKU/tier. See [Azure App Service Plans](https://learn.microsoft.com/en-us/azure/app-service/overview-hosting-plans). |
| **SkuNotAvailable**                                           | Requested SKU not available in the selected location/zone | Check SKU availability with `az appservice list-locations --sku <sku-name>` and pick a supported region or SKU.                                                                                                                                                                          |

## Regional & Location Issues

| Issue/Error Code                                         | Description                                                                   | Steps to Resolve                                                                                                                                                                                                                                                                     |
| -------------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **LocationNotAvailableForResourceType**                  | Resource type not supported in the selected region                            | Verify availability with `az provider show --namespace <provider-namespace> --query "resourceTypes[?resourceType=='<resource-type>'].locations" -o table`, or check [Azure Products by Region](https://azure.microsoft.com/en-us/explore/global-infrastructure/products-by-region/). |
| **InvalidResourceLocation**                              | Cannot change region for already-deployed resources                           | Azure resources cannot change region after creation. Either delete and redeploy (`azd down --force --purge` then `azd up`), or create a new environment in a different region (`azd env new <name>`, `azd env set AZURE_LOCATION <region>`, `azd up`). Back up critical data first.  |
| **DeploymentModelNotSupported / ServiceModelDeprecated** | Foundry/Azure OpenAI model not supported or deprecated in the selected region | Verify model/region availability in [Azure AI Foundry models](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/concepts/models).                                                                                                                                            |

## Resource Naming & Validation

| Issue/Error Code                      | Description                                      | Steps to Resolve                                                                                                                                                                                                  |
| ------------------------------------- | ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ResourceNameInvalid**               | Resource name violates naming convention rules   | Confirm the name is within the allowed length/characters for that resource type; see [Resource Naming Convention](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/resource-name-rules). |
| **Workspace Name - InvalidParameter** | Workspace name does not meet the required format | Must start/end with an alphanumeric character, only `a-z`/`0-9`/`-`, no spaces/underscores/periods, unique within region and subscription, 3-33 characters.                                                       |

## Resource Identification & References

| Issue/Error Code                                                                 | Description                                                              | Steps to Resolve                                                                                                                                                                                                                                                                                                   |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **ResourceNotFound / ParentResourceNotFound / DeploymentOutputEvaluationFailed** | Invalid or non-existent resource ID reference                            | Verify the resource ID format and that it exists, and that its provisioning state is `Succeeded` (`az resource show --ids <Resource ID> --query "properties.provisioningState"`). See [Resource Not Found errors](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/error-not-found). |
| **PrincipalNotFound**                                                            | Principal ID does not exist in the Azure AD tenant, or replication delay | Verify the principal exists in the same tenant (`az ad sp show --id <object-id>`); if just created, wait a few minutes and retry; explicitly set `principalType` in Terraform/ARM to avoid replication-delay issues.                                                                                               |

## Resource Group & Deployment Management

| Issue/Error Code              | Description                                                      | Steps to Resolve                                                                                                                                                                                                          |
| ----------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ResourceGroupNotFound**     | Specified resource group does not exist                          | Confirm the resource group exists in the Azure Portal, or create a new environment before redeploying: `azd env new <env-name>` (this error can also happen when reusing a stale `.env` file from a previous deployment). |
| **ResourceGroupBeingDeleted** | Resource group is currently being deleted                        | Wait for deletion to finish, then create a new one or use a different resource group.                                                                                                                                     |
| **DeploymentActive**          | Another deployment is already in progress in this resource group | Wait for the in-progress deployment to finish before starting a new one.                                                                                                                                                  |
| **DeploymentCanceled**        | Deployment was canceled before completion                        | Check the deployment history in the Azure Portal (Resource Group → Deployments) for the root cause, fix it, and retry.                                                                                                    |

## Resource State & Provisioning

| Issue/Error Code                              | Description                                                                         | Steps to Resolve                                                                                                                                                                                                                                                                                                                            |
| --------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **AccountProvisioningStateInvalid**           | Resource used before provisioning completed                                         | Wait until the resource's provisioning state is `Succeeded` before using it.                                                                                                                                                                                                                                                                |
| **FlagMustBeSetForRestore / NameUnavailable** | Soft-deleted Cognitive Services/Foundry resource requires a restore flag or a purge | Either restore (`"restore": true` in the resource definition) or purge the deleted resource first: `az cognitiveservices account purge --name <name> --resource-group <rg> --location <location>`. See [Soft delete and resource restore](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/delete-resource-group). |

---

💡 If you encounter an error not listed here, check the
[Common Deployment Errors](https://learn.microsoft.com/en-us/azure/azure-resource-manager/troubleshooting/common-deployment-errors)
documentation, or [Terraform's azurerm provider troubleshooting](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs).
