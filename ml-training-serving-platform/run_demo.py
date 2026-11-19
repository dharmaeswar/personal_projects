"""End-to-end demo: train -> register -> promote -> serve -> canary -> drift
check -> rollback. All data synthetic.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ml_platform.backfill import backfill
from ml_platform.data import generate_applications
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


if __name__ == "__main__":
    main()
