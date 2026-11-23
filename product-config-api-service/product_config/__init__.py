"""Product Config API Service.

An API-first product-configuration service: modular, configurable product
capabilities exposed as a REST microservice, built the way a cloud-native
internal tooling team would build one -- small Lambda-style handlers, a
DynamoDB-style key-value store, a Step Functions-style publish workflow,
Terraform infrastructure as code, and a CI pipeline that runs the tests.

Demo project. All products, attributes, and traffic are synthetic.
Nothing here describes a real Nike system, real products, or real data.
"""

__all__ = ["models", "store", "service", "handlers", "api", "ai_assist"]
