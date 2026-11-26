variable "synapse_sql_password" {
  description = "SQL admin password for the Synapse workspace (pass via TF_VAR_synapse_sql_password; never commit a real value)."
  type        = string
  sensitive   = true
}
