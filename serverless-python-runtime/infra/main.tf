# Example Terraform for the serverless Python runtime service.
# Declares the service the way a team would deploy it: one function,
# its memory/timeout envelope, and a bundle built by runtime.packaging.
# Example only — not a tested deployment.

terraform {
  required_version = ">= 1.5"
}

variable "function_name" {
  type    = string
  default = "serverless-python-runtime"
}

variable "memory_mb" {
  type    = number
  default = 512
}

variable "timeout_s" {
  type    = number
  default = 30
}

variable "bundle_budget_mb" {
  type    = number
  default = 250
}

# Placeholder resource: replace with the real provider's function resource
# (e.g. aws_lambda_function) when deploying for real.
resource "null_resource" "runtime_service" {
  triggers = {
    function_name    = var.function_name
    memory_mb        = var.memory_mb
    timeout_s        = var.timeout_s
    bundle_budget_mb = var.bundle_budget_mb
    runtime          = "python3.12"
  }
}

output "function_name" {
  value = var.function_name
}

output "execution_envelope" {
  value = {
    memory_mb        = var.memory_mb
    timeout_s        = var.timeout_s
    bundle_budget_mb = var.bundle_budget_mb
  }
}
