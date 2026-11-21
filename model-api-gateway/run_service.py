"""Demo entry point: seeds keys and model backends, serves on :8000."""

import os

from gateway.api import Gateway, serve
from gateway.router import Backend
from gateway.serving import ModelVersion

# Demo predictive model: a churn-risk scorer with a validated input schema.
DEMO_PREDICTIVE_MODELS = [
    ModelVersion(
        "churn-risk", "1.2.0", "scikit-learn",
        [{"name": "tenure_months", "type": "number", "required": True,
          "minimum": 0, "maximum": 600},
         {"name": "monthly_spend", "type": "number", "required": True,
          "minimum": 0, "maximum": 100000},
         {"name": "support_tickets", "type": "number", "required": True,
          "minimum": 0, "maximum": 100},
         {"name": "is_enterprise", "type": "boolean", "required": False}],
        "churn_probability",
        description="Demo churn-risk scorer: probability a customer churns."),
]

DEMO_KEYS = {
    "sk-demo-pro-1": ("demo-pro", "pro", ("models:invoke", "usage:read", "billing:read")),
    "sk-demo-free-1": ("demo-free", "free", ("models:invoke", "usage:read")),
}


def build_gateway():
    gateway = Gateway()
    for raw_key, (owner, tier, scopes) in DEMO_KEYS.items():
        gateway.keys.add_seeded(raw_key, owner, tier, scopes)
    for model, backends in {
        "llama-4-scout": [("gpu-us-east-1", 120.0, 32), ("gpu-us-west-1", 180.0, 32)],
        "qwen3-32b": [("gpu-us-east-2", 90.0, 48)],
        "deepseek-r1-distill": [("gpu-eu-1", 150.0, 16), ("gpu-us-east-3", 140.0, 16)],
    }.items():
        for backend_id, latency, capacity in backends:
            gateway.registry.register(Backend(backend_id, model, latency, capacity))
    for model_version in DEMO_PREDICTIVE_MODELS:
        gateway.serving_registry.register(model_version)
    return gateway


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print("Model API Gateway on http://127.0.0.1:%d" % port)
    print("Demo keys: %s" % ", ".join(DEMO_KEYS))
    serve(build_gateway(), port=port)
