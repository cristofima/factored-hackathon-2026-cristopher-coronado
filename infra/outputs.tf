output "AZURE_LOCATION" { value = var.location }
output "AZURE_TENANT_ID" { value = data.azurerm_client_config.current.tenant_id }
output "AZURE_RESOURCE_GROUP" { value = data.azurerm_resource_group.main.name }

output "AZURE_ACCOUNT_NAME" { value = azapi_resource.app["account"].name }
output "AZURE_PAYMENT_NAME" { value = azapi_resource.app["payment"].name }
output "AZURE_TRANSACTION_NAME" { value = azapi_resource.app["transaction"].name }
output "AZURE_WEB_NAME" { value = azapi_resource.app["web"].name }
output "AZURE_RESPONSES_BFF_NAME" { value = azapi_resource.responses_bff.name }

output "ACCOUNT_URI" { value = "https://${azapi_resource.app["account"].output.properties.defaultHostName}" }
output "PAYMENT_URI" { value = "https://${azapi_resource.app["payment"].output.properties.defaultHostName}" }
output "TRANSACTION_URI" { value = "https://${azapi_resource.app["transaction"].output.properties.defaultHostName}" }
output "WEB_URI" { value = "https://${azapi_resource.app["web"].output.properties.defaultHostName}" }
output "RESPONSES_BFF_URI" { value = "https://${azapi_resource.responses_bff.output.properties.defaultHostName}" }

output "AZURE_STORAGE_ACCOUNT" { value = azurerm_storage_account.content.name }
output "AZURE_STORAGE_CONTAINER" { value = azurerm_storage_container.content.name }
output "AZURE_STORAGE_RESOURCE_GROUP" { value = data.azurerm_resource_group.main.name }

output "AZURE_AI_FOUNDRY_ACCOUNT_NAME" { value = azapi_resource.foundry_account_dedicated.name }
output "AZURE_AI_FOUNDRY_PROJECT_NAME" { value = azapi_resource.foundry_project.name }
output "AZURE_OPENAI_ENDPOINT" { value = azapi_resource.foundry_account_dedicated.output.properties.endpoint }
output "FOUNDRY_PROJECT_ENDPOINT" { value = "https://${azapi_resource.foundry_account_dedicated.name}.services.ai.azure.com/api/projects/${azapi_resource.foundry_project.name}" }
