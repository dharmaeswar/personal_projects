"""Agentic demo: an agent validates, packages, and promotes a candidate model.

Runs the validate_and_promote task end to end — train a candidate, run the
promotion gate against production, export a checksummed package, then
promote with explicit approval — followed by a drift-response check.
All data is synthetic.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ml_platform.agent_runtime import AgentRuntime, build_platform_tools
from ml_platform.data import generate_applications
from ml_platform.registry import Registry
from ml_platform.serving import ServingService
from ml_platform.training import evaluate, train

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    registry = Registry(os.path.join(BASE, "registry.json"))
    train_rows = generate_applications(2000, seed=42)
    eval_rows = generate_applications(500, seed=99)

    # Seed production so the gate has something to compare against. The
    # seeded model is trained lightly (50 epochs); the agent's candidate
    # trains fully, so it clears the no-regression bar (min_improvement 0.0
    # — the synthetic data saturates near AUC 0.70, so the demo gates on
    # "no worse than production" rather than a strict improvement).
    if registry.production_version() is None:
        model_v1 = train(train_rows, epochs=50, seed=7)
        v1 = registry.register("credit-decision", model_v1, evaluate(model_v1, eval_rows))
        registry.promote(v1)
        print(f"seeded production {v1}")

    serving = ServingService(registry, train_rows)
    tools = build_platform_tools(registry, train_rows, eval_rows, serving=serving)
    print("tools:", [t["name"] for t in tools.list_tools()])

    agent = AgentRuntime(tools)
    result = agent.run(
        "validate_and_promote",
        task_args={"evaluate_candidate": {"min_improvement": 0.0},
                   "promote_model": {"approved": True},
                   "package_model": {"out_dir": BASE}})
    print(json.dumps(result, indent=2, default=str))

    drift = agent.run("drift_response")
    print("drift response:", drift["trace"][0]["result"]["recommendation"])


if __name__ == "__main__":
    main()
