# Databricks / Azure lakehouse infrastructure (plan-only — NOT applied).
# Declares the resources the pipeline maps to: resource group, ADLS Gen2
# storage, Azure Data Factory, Synapse workspace, and a Databricks workspace.
# Run `terraform plan` to review; nothing here provisions real cloud resources.

terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 3.0" }
    databricks = { source = "databricks/databricks", version = "~> 1.0" }
  }
}

variable "location" { default = "East US" }
variable "environment" { default = "dev" }

resource "azurerm_resource_group" "claims" {
  name     = "rg-claims-${var.environment}"
  location = var.location
}

resource "azurerm_storage_account" "lake" {
  name                     = "stclaims${var.environment}"
  resource_group_name      = azurerm_resource_group.claims.name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  is_hns_enabled           = true # ADLS Gen2 hierarchical namespace
}

resource "azurerm_storage_data_lake_gen2_filesystem" "bronze" {
  name               = "bronze"
  storage_account_id = azurerm_storage_account.lake.id
}

resource "azurerm_storage_data_lake_gen2_filesystem" "silver" {
  name               = "silver"
  storage_account_id = azurerm_storage_account.lake.id
}

resource "azurerm_storage_data_lake_gen2_filesystem" "gold" {
  name               = "gold"
  storage_account_id = azurerm_storage_account.lake.id
}

resource "azurerm_data_factory" "claims" {
  name                = "adf-claims-${var.environment}"
  location            = var.location
  resource_group_name = azurerm_resource_group.claims.name
}

resource "azurerm_synapse_workspace" "claims" {
  name                                 = "syn-claims-${var.environment}"
  resource_group_name                  = azurerm_resource_group.claims.name
  location                             = var.location
  storage_data_lake_gen2_filesystem_id = azurerm_storage_data_lake_gen2_filesystem.gold.id
  sql_administrator_login              = "sqladmin"
  sql_administrator_login_password     = var.synapse_sql_password
}

resource "databricks_workspace" "claims" {
  name                = "dbw-claims-${var.environment}"
  resource_group_name = azurerm_resource_group.claims.name
  location            = var.location
  sku                 = "standard"
}
