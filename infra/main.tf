data "azurerm_client_config" "current" {}

data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

locals {
  token = lower(replace(var.environment_name, "-", ""))
  tags  = merge(var.tags, { "azd-env-name" = var.environment_name })
  apps = {
    for service in ["account", "transaction"] :
    service => lookup(var.app_names, service, "app-${service}-${var.environment_name}")
  }
  web_name = lookup(var.app_names, "web", "app-banking-web-${var.environment_name}")
  # azurerm_service_plan.main.id returns "/providers/Microsoft.Web/serverFarms/..." (capital F), but
  # Azure's API echoes back lowercase "serverfarms" on read-back, which otherwise causes a perpetual
  # diff on every azapi_resource site (and cascades their computed outputs to "known after apply").
  service_plan_id          = "/subscriptions/${var.subscription_id}/resourceGroups/${data.azurerm_resource_group.main.name}/providers/Microsoft.Web/serverfarms/${azurerm_service_plan.main.name}"
  storage_name             = coalesce(var.storage_account_name, substr("st${local.token}", 0, 24))
  foundry_account_name     = coalesce(var.foundry_account_name, "aif${substr(local.token, 0, 15)}${substr(sha1(var.subscription_id), 0, 6)}")
  foundry_project_name     = coalesce(var.foundry_project_name, "foundry-${var.environment_name}")
  foundry_project_endpoint = "https://${local.foundry_account_name}.services.ai.azure.com/api/projects/${local.foundry_project_name}"
  responses_bff_name       = lookup(var.app_names, "responses-bff", "app-responses-bff-${var.environment_name}")
  postgres_server_name     = coalesce(var.postgres_server_name, "pg-${var.environment_name}")
  postgres_database_url    = "postgresql+psycopg://${urlencode(var.postgres_admin_username)}:${urlencode(var.postgres_admin_password)}@${azapi_resource.postgres_server.output.properties.fullyQualifiedDomainName}:5432/${urlencode(var.postgres_database_name)}?sslmode=require"
  key_vault_name           = coalesce(var.key_vault_name, "kv${substr(local.token, 0, 15)}${substr(sha1(var.subscription_id), 0, 6)}")
  # Shared secrets stored once in Key Vault and referenced from app settings via @Microsoft.KeyVault(...);
  # see plan/tmp/KEY_VAULT_SECRETS_MIGRATION_PLAN.md. jwt-secret-key/internal-identity-secret are
  # uploaded manually (Terraform never learns their value); database-url IS set by Terraform below,
  # since Terraform already holds the PostgreSQL admin password in state to build the connection string.
  jwt_secret_key_reference           = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault.secrets.vault_uri}secrets/jwt-secret-key/)"
  internal_identity_secret_reference = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault.secrets.vault_uri}secrets/internal-identity-secret/)"
  database_url_reference             = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault.secrets.vault_uri}secrets/database-url/)"
}

resource "azurerm_key_vault" "secrets" {
  name                       = local.key_vault_name
  location                   = data.azurerm_resource_group.main.location
  resource_group_name        = data.azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = true
  tags                       = local.tags
}

resource "azurerm_role_assignment" "account_key_vault_secrets_user" {
  scope                = azurerm_key_vault.secrets.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azapi_resource.app["account"].output.identity.principalId
}

resource "azurerm_role_assignment" "transaction_key_vault_secrets_user" {
  scope                = azurerm_key_vault.secrets.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azapi_resource.app["transaction"].output.identity.principalId
}

resource "azurerm_role_assignment" "responses_bff_key_vault_secrets_user" {
  scope                = azurerm_key_vault.secrets.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azapi_resource.responses_bff.output.identity.principalId
}

# Grants the GitHub Actions federated identity read access so cd-hosted-agent.yaml can resolve
# internal-identity-secret directly (Foundry hosted agents have no native Key Vault reference).
resource "azurerm_role_assignment" "github_actions_key_vault_secrets_user" {
  count                = var.github_actions_principal_id == null ? 0 : 1
  scope                = azurerm_key_vault.secrets.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = var.github_actions_principal_id
}

# Grants whoever runs `terraform apply`/`azd provision` write access so Terraform can create the
# database-url secret below; Key Vault RBAC does not inherit from subscription Owner/Contributor.
resource "azurerm_role_assignment" "deployer_key_vault_secrets_officer" {
  count                = var.deployer_principal_id == null ? 0 : 1
  scope                = azurerm_key_vault.secrets.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = var.deployer_principal_id
}

# Terraform already holds the PostgreSQL admin password in state to build this connection string,
# so storing it in Key Vault adds no new state exposure; unlike jwt-secret-key/internal-identity-secret,
# this secret's value IS managed here, not uploaded manually.
resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  value        = local.postgres_database_url
  key_vault_id = azurerm_key_vault.secrets.id
  depends_on   = [azurerm_role_assignment.deployer_key_vault_secrets_officer]
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${var.environment_name}"
  location            = data.azurerm_resource_group.main.location
  resource_group_name = data.azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_application_insights" "main" {
  name                = "appi-${var.environment_name}"
  location            = data.azurerm_resource_group.main.location
  resource_group_name = data.azurerm_resource_group.main.name
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.main.id
  tags                = local.tags
}

resource "azurerm_service_plan" "main" {
  name                = "asp-${var.environment_name}"
  location            = data.azurerm_resource_group.main.location
  resource_group_name = data.azurerm_resource_group.main.name
  os_type             = "Linux"
  sku_name            = var.plan_sku
  tags                = local.tags
}

# AzAPI creates the site so Azure's unique default hostname is set on the first PUT.
# An azurerm web app followed by an AzAPI patch would be too late for this setting.
# Kept as its own resource (not part of azapi_resource.app's for_each) because account/transaction
# need to reference its hostname for CORS, and Terraform forbids a for_each resource instance from
# referencing another instance of the same resource address ("self-referential block").
resource "azapi_resource" "web" {
  type      = "Microsoft.Web/sites@2024-11-01"
  name      = local.web_name
  location  = data.azurerm_resource_group.main.location
  parent_id = data.azurerm_resource_group.main.id
  tags      = merge(local.tags, { "azd-service-name" = "web" })
  identity {
    type = "SystemAssigned"
  }
  body = {
    kind = "app,linux"
    properties = merge({
      serverFarmId = local.service_plan_id
      httpsOnly    = true
      siteConfig = {
        linuxFxVersion = "NODE|22-lts"
        # Always On is supported from Basic (B1) up; only Free/Shared tiers lack it.
        alwaysOn = var.plan_sku != "F1"
        # web serves azd's "dist" deployment artifact directly as wwwroot (azure.yaml services.web.dist: dist),
        # not a nested dist/ subfolder, and skips SCM_DO_BUILD_DURING_DEPLOYMENT/POST_BUILD_COMMAND entirely:
        # the deploy zip contains only the already-built static output, no package.json, so there is nothing
        # for Oryx to rebuild. A remote Oryx rebuild previously re-baked VITE_* from .env.local on the server,
        # silently overwriting azd's correctly built-time-injected values (see .github/workflows/README.md).
        appCommandLine = "pm2 serve /home/site/wwwroot --no-daemon --spa"
        appSettings = [
          { name = "WEBSITES_PORT", value = "8080" },
          { name = "APPLICATIONINSIGHTS_CONNECTION_STRING", value = azurerm_application_insights.main.connection_string }
        ]
      }
      }, var.hostname_scope == null ? {} : {
      autoGeneratedDomainNameLabelScope = var.hostname_scope
    })
  }
  response_export_values = ["properties.defaultHostName", "identity.principalId"]
}

resource "azapi_resource" "app" {
  for_each  = local.apps
  type      = "Microsoft.Web/sites@2024-11-01"
  name      = each.value
  location  = data.azurerm_resource_group.main.location
  parent_id = data.azurerm_resource_group.main.id
  tags      = merge(local.tags, { "azd-service-name" = each.key })
  identity {
    type = "SystemAssigned"
  }
  body = {
    kind = "app,linux"
    properties = merge({
      serverFarmId = local.service_plan_id
      httpsOnly    = true
      siteConfig = {
        linuxFxVersion = "PYTHON|3.11"
        # Always On is supported from Basic (B1) up; only Free/Shared tiers lack it.
        alwaysOn       = var.plan_sku != "F1"
        appCommandLine = "python -m uvicorn main:app --host 0.0.0.0 --port 8080"
        appSettings = concat([
          { name = "WEBSITES_PORT", value = "8080" },
          { name = "APPLICATIONINSIGHTS_CONNECTION_STRING", value = azurerm_application_insights.main.connection_string },
          { name = "SCM_DO_BUILD_DURING_DEPLOYMENT", value = "true" },
          { name = "PORT", value = "8080" }
          ], contains(["account", "transaction"], each.key) ? [
          { name = "DATABASE_URL", value = local.database_url_reference },
          { name = "CORS_ALLOWED_ORIGINS", value = "https://${azapi_resource.web.output.properties.defaultHostName}" },
          { name = "JWT_SECRET_KEY", value = local.jwt_secret_key_reference },
          { name = "INTERNAL_IDENTITY_SECRET", value = local.internal_identity_secret_reference }
        ] : [])
        # Native App Service CORS is intentionally cleared (not merely omitted) here: Microsoft's own
        # docs state it takes precedence over and disables the app's own CORS code entirely when both
        # are set (https://learn.microsoft.com/en-us/azure/app-service/app-service-web-tutorial-rest-api#app-service-cors-vs-your-cors).
        # Omitting the cors key entirely does NOT clear a previously-set value, the siteConfig API
        # treats an absent property as "leave unchanged", not "remove"; an explicit empty array is
        # required. Each service's own CORSMiddleware (CORS_ALLOWED_ORIGINS/main.py) is the single
        # source of truth for CORS.
        cors = {
          allowedOrigins     = []
          supportCredentials = false
        }
      }
      }, var.hostname_scope == null ? {} : {
      autoGeneratedDomainNameLabelScope = var.hostname_scope
    })
  }
  response_export_values = ["properties.defaultHostName", "identity.principalId"]

  # CORS_ALLOWED_ORIGINS/JWT_SECRET_KEY/INTERNAL_IDENTITY_SECRET/DATABASE_URL/cors all live directly in
  # this one resource (no separate api_cors patch resource anymore), so Terraform is the single owner of
  # the full appSettings array and no ignore_changes/manual az webapp config appsettings set is needed;
  # see plan/tmp/KEY_VAULT_SECRETS_MIGRATION_PLAN.md.
  depends_on = [azurerm_key_vault_secret.database_url]
}

resource "azapi_resource" "responses_bff" {
  type      = "Microsoft.Web/sites@2024-11-01"
  name      = local.responses_bff_name
  location  = data.azurerm_resource_group.main.location
  parent_id = data.azurerm_resource_group.main.id
  tags      = merge(local.tags, { "azd-service-name" = "responses-bff" })

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "app,linux"
    properties = merge({
      serverFarmId = local.service_plan_id
      httpsOnly    = true
      siteConfig = {
        linuxFxVersion = "PYTHON|3.11"
        # Always On is supported from Basic (B1) up; only Free/Shared tiers lack it.
        alwaysOn       = var.plan_sku != "F1"
        appCommandLine = "python -m uvicorn bff.main:app --host 0.0.0.0 --port 8080"
        # Native App Service CORS is intentionally cleared (not merely omitted) here: Microsoft's own
        # docs state it takes precedence over and disables the app's own CORS code entirely when both
        # are set (https://learn.microsoft.com/en-us/azure/app-service/app-service-web-tutorial-rest-api#app-service-cors-vs-your-cors),
        # which would silently drop the X-Conversation-Id exposed header bff/main.py's CORSMiddleware
        # sets. Omitting the cors key entirely does NOT clear a previously-set value, the siteConfig
        # API treats an absent property as "leave unchanged", not "remove"; an explicit empty array
        # is required.
        cors = {
          allowedOrigins     = []
          supportCredentials = false
        }
        appSettings = [
          { name = "WEBSITES_PORT", value = "8080" },
          { name = "PORT", value = "8080" },
          { name = "APPLICATIONINSIGHTS_CONNECTION_STRING", value = azurerm_application_insights.main.connection_string },
          { name = "SCM_DO_BUILD_DURING_DEPLOYMENT", value = "true" },
          { name = "PROFILE", value = "prod" },
          { name = "RESPONSES_UPSTREAM_MODE", value = "foundry" },
          # The Foundry Agent Service protocol endpoint requires an explicit api-version
          # (unlike the generic Azure OpenAI /openai/v1/responses surface, where it's optional);
          # see evals/run_held_out_eval.py, which already hardcodes the same value.
          { name = "RESPONSES_AGENT_ENDPOINT", value = "${local.foundry_project_endpoint}/agents/home-banking-agent/endpoint/protocols/openai/responses?api-version=v1" },
          { name = "DATABASE_URL", value = local.database_url_reference },
          { name = "ALLOWED_ORIGINS", value = jsonencode(["https://${azapi_resource.web.output.properties.defaultHostName}"]) },
          { name = "JWT_SECRET_KEY", value = local.jwt_secret_key_reference },
          { name = "INTERNAL_IDENTITY_SECRET", value = local.internal_identity_secret_reference }
        ]
      }
      }, var.hostname_scope == null ? {} : {
      autoGeneratedDomainNameLabelScope = var.hostname_scope
    })
  }
  response_export_values = ["properties.defaultHostName", "identity.principalId"]

  # JWT_SECRET_KEY/INTERNAL_IDENTITY_SECRET/DATABASE_URL are Key Vault references declared directly
  # here (see plan/tmp/KEY_VAULT_SECRETS_MIGRATION_PLAN.md); this is the single owner of this site's
  # appSettings, so no ignore_changes/manual az webapp config appsettings set is needed.
  depends_on = [azurerm_key_vault_secret.database_url]
}


resource "azurerm_storage_account" "content" {
  name                            = local.storage_name
  location                        = data.azurerm_resource_group.main.location
  resource_group_name             = data.azurerm_resource_group.main.name
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  allow_nested_items_to_be_public = false
  tags                            = local.tags

  blob_properties {
    delete_retention_policy {
      days = 2
    }
  }
}

resource "azurerm_storage_container" "content" {
  name                  = var.storage_container_name
  storage_account_id    = azurerm_storage_account.content.id
  container_access_type = "private"
}

resource "azapi_resource" "postgres_server" {
  type      = "Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01"
  parent_id = data.azurerm_resource_group.main.id
  name      = local.postgres_server_name
  location  = coalesce(var.postgres_location, data.azurerm_resource_group.main.location)
  tags      = local.tags

  body = {
    properties = {
      administratorLogin         = var.postgres_admin_username
      administratorLoginPassword = var.postgres_admin_password
      authConfig = {
        activeDirectoryAuth = "Disabled"
        passwordAuth        = "Enabled"
      }
      backup = {
        backupRetentionDays = var.postgres_backup_retention_days
        geoRedundantBackup  = "Disabled"
      }
      createMode = "Default"
      highAvailability = {
        mode = "Disabled"
      }
      network = {
        publicNetworkAccess = "Enabled"
      }
      storage = {
        storageSizeGB = var.postgres_storage_mb / 1024
      }
      version = var.postgres_version
    }
    sku = {
      name = trimprefix(var.postgres_sku_name, "B_")
      tier = "Burstable"
    }
  }

  response_export_values = [
    "properties.administratorLogin",
    "properties.fullyQualifiedDomainName",
  ]
}

resource "azapi_resource" "postgres_database" {
  type      = "Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01"
  parent_id = azapi_resource.postgres_server.id
  name      = var.postgres_database_name

  body = {
    properties = {
      charset   = "UTF8"
      collation = "en_US.utf8"
    }
  }
}

resource "azapi_resource" "postgres_allow_azure_services" {
  type      = "Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01"
  parent_id = azapi_resource.postgres_server.id
  name      = "AllowAllAzureServicesAndResourcesWithinAzureIps"

  body = {
    properties = {
      startIpAddress = "0.0.0.0"
      endIpAddress   = "0.0.0.0"
    }
  }
}

# Opt-in: only created when postgres_allowed_client_ip is set, for example to let a
# developer reach the server directly from pgAdmin.
resource "azapi_resource" "postgres_allow_local_client" {
  count     = var.postgres_allowed_client_ip != null && var.postgres_allowed_client_ip != "" ? 1 : 0
  type      = "Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01"
  parent_id = azapi_resource.postgres_server.id
  name      = "AllowLocalClientIp"

  body = {
    properties = {
      startIpAddress = var.postgres_allowed_client_ip
      endIpAddress   = var.postgres_allowed_client_ip
    }
  }
}

resource "azapi_resource" "foundry_account_dedicated" {
  type                      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name                      = local.foundry_account_name
  location                  = data.azurerm_resource_group.main.location
  parent_id                 = data.azurerm_resource_group.main.id
  schema_validation_enabled = false
  tags                      = local.tags
  identity {
    type = "SystemAssigned"
  }
  body = {
    kind = "AIServices"
    sku = {
      name = "S0"
    }
    properties = {
      customSubDomainName    = local.foundry_account_name
      disableLocalAuth       = false
      publicNetworkAccess    = "Enabled"
      allowProjectManagement = true
    }
  }
  response_export_values = ["properties.endpoint"]
}

resource "azapi_resource" "foundry_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name      = local.foundry_project_name
  parent_id = azapi_resource.foundry_account_dedicated.id
  location  = data.azurerm_resource_group.main.location
  tags      = local.tags
  identity {
    type = "SystemAssigned"
  }
  body = {
    properties = {}
  }
}

resource "azurerm_role_assignment" "responses_bff_agent_consumer" {
  scope                            = azapi_resource.foundry_project.id
  role_definition_name             = "Foundry Agent Consumer"
  principal_id                     = azapi_resource.responses_bff.output.identity.principalId
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}

resource "azurerm_role_definition" "foundry_user_identity_impersonation" {
  name               = "Foundry Agent User Identity Impersonation"
  role_definition_id = uuidv5("url", "${data.azurerm_resource_group.main.id}/roles/foundry-agent-user-identity-impersonation")
  scope              = data.azurerm_resource_group.main.id
  description        = "Allows a trusted middle tier to delegate an authenticated end-user identity to Foundry hosted agents."

  permissions {
    data_actions = [
      "Microsoft.CognitiveServices/accounts/AIServices/agents/endpoints/UserIdentityImpersonation/action",
    ]
  }

  assignable_scopes = [data.azurerm_resource_group.main.id]
}

resource "azurerm_role_assignment" "responses_bff_user_identity_impersonation" {
  scope                            = azapi_resource.foundry_project.id
  role_definition_id               = azurerm_role_definition.foundry_user_identity_impersonation.role_definition_resource_id
  principal_id                     = azapi_resource.responses_bff.output.identity.principalId
  principal_type                   = "ServicePrincipal"
  skip_service_principal_aad_check = true
}
