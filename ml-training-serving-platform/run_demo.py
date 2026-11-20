"""End-to-end demo: train -> register -> promote -> serve -> canary -> drift
check -> rollback. All data synthetic.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ml_platform.backfill import backfill
from ml_platform.data import generate_applications
from ml_platform.decisioning import (
    DecisioningEngine,
    generate_members,
    log_decision,
    outcome_report,
    read_decisions,
)
from ml_platform.registry import Registry
from ml_platform.serving import ServingService
from ml_platform.training import evaluate, train, train_pipeline

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    registry = Registry(os.path.join(BASE, "registry.json"))
    model_v1, metrics_v1, train_rows = train_pipeline(n_train=2000, n_test=500)
    v1 = registry.register("credit-decision", model_v1, metrics_v1)
    registry.promote(v1)
    print(f"registered + promoted {v1}: {metrics_v1}")

    model_v2, metrics_v2, _ = train_pipeline(n_train=2000, n_test=500, seed=123)
    v2 = registry.register("credit-decision", model_v2, metrics_v2)
    print(f"registered candidate {v2}: {metrics_v2}")

    service = ServingService(registry, train_rows)
    for app_id, (features, _label) in enumerate(generate_applications(200, seed=99)):
        service.predict(app_id, features)
    print("latency:", service.latency_stats(), "error rate:", round(service.error_rate(), 4))

    service.start_canary(v2, share=0.2)
    canary_hits = sum(
        1 for app_id, (features, _l) in enumerate(generate_applications(200, seed=7), start=1000)
        if service.predict(app_id, features)["version"] == v2
    )
    print(f"canary: {canary_hits}/200 requests routed to {v2}")
    print("drift:", {k: v for k, v in service.drift_report().items() if v["psi"] is not None})

    out, n, mean_p = backfill(registry, v2, generate_applications(100, seed=5),
                              os.path.join(BASE, "backfill_v2.csv"))
    print(f"backfill: {n} rows scored with {v2}, mean default prob {mean_p} -> {out}")

    registry.promote(v2)
    print(f"promoted {v2} to production after backfill comparison")
    rolled = service.rollback()
    print(f"rollback restored production to {rolled} (expected {v1})")

    # Decisioning: score next-best-actions with the production model,
    # apply business rules, log decisions, and compare outcomes against
    # the rule-only baseline. All member data is synthetic.
    engine = DecisioningEngine(registry)
    log_path = os.path.join(BASE, "decisions.jsonl")
    if os.path.exists(log_path):
        os.remove(log_path)
    members = generate_members(20, seed=2026)
    for member in members:
        decision = engine.decide_with_baseline(member)
        log_decision(log_path, decision)
    logged = read_decisions(log_path)
    print(f"decisioning: {len(logged)} decisions logged to decisions.jsonl "
          f"with production model {registry.production_version()}")
    example = next(d for d in logged if d["chosen_action"] is not None)
    print("  example:", {k: example[k] for k in
                         ("member_id", "chosen_action", "model_version", "scores", "rules_applied")})
    # Synthetic outcomes for every (member, action) pair: a member accepts
    # an action with a probability that rises with its score (seeded,
    # reproducible). Covering all actions lets the outcome report compare
    # the model-chosen action against the rule-only baseline fairly.
    import random
    rng = random.Random(7)
    outcomes = []
    for d in logged:
        for action_id, score in d["scores"].items():
            outcomes.append({"member_id": d["member_id"], "action": action_id,
                             "accepted": rng.random() < score})
    report = outcome_report(logged, outcomes)
    print("  outcomes:", report["model_chosen"], "baseline:", report["rule_only_baseline"],
          "lift:", report["lift_vs_baseline"])


if __name__ == "__main__":
    main()
