variable "subscription_id" {
  description = "Subscription containing the single resource group."
  type        = string
}

variable "environment_name" {
  description = "Single azd environment name used to derive resource names."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9-]{1,18}$", var.environment_name))
    error_message = "Use 1-18 lowercase letters, digits or hyphens."
  }
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  description = "Existing single resource group name selected for this stack."
  type        = string
}

variable "plan_sku" {
  type    = string
  default = "B1"
}

variable "app_names" {
  description = "Override app names to import already deployed apps without replacement."
  type        = map(string)
  default     = {}
}

variable "hostname_scope" {
  description = "Set only at creation; null keeps existing legacy hostnames when importing sites."
  type        = string
  default     = "TenantReuse"
  validation {
    condition     = var.hostname_scope == null || contains(["TenantReuse", "SubscriptionReuse", "ResourceGroupReuse", "NoReuse"], var.hostname_scope)
    error_message = "Use a supported Azure App Service unique hostname scope or null."
  }
}

variable "storage_account_name" {
  type    = string
  default = null
}

variable "storage_container_name" {
  type    = string
  default = "content"
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "foundry_account_name" {
  description = "Optional override for the dedicated AI Services (Foundry) account name."
  type        = string
  default     = null
}

variable "foundry_project_name" {
  description = "Optional override for the dedicated Foundry project name."
  type        = string
  default     = null
}
