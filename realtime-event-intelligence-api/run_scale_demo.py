"""Streaming-at-scale demo: anomaly detection + backpressure + API versions.

Seeds synthetic per-window telemetry counts with a spike, runs the
z-score / MAD / rules detectors, correlates across sources, triangulates
a bottleneck, recommends a backpressure action, and checks a v2 API
contract against v1. Prints a JSON summary.

Usage:
    python run_scale_demo.py
"""

from __future__ import annotations

import json

from event_intel.anomaly import (correlate, mad_detect, rule_detect,
                                 zscore_detect)
from event_intel.apiversion import ApiContract, check_backward_compat
from event_intel.backpressure import (BackpressureController, StageMetrics,
                                      cost_for_throughput, triangulate)

COUNTS_A = [20, 21, 19, 20, 22, 20, 19, 21, 20, 20, 90, 21, 20, 19, 20]
COUNTS_B = [15, 16, 14, 15, 15, 16, 14, 15, 15, 15, 88, 16, 15, 14, 15]


def main() -> int:
    detectors = [
        zscore_detect("sensor-a", COUNTS_A),
        zscore_detect("sensor-b", COUNTS_B),
        mad_detect("sensor-a", COUNTS_A),
        rule_detect("sensor-a", COUNTS_A, max_count=50),
    ]
    signals = correlate(detectors)
    stages = [
        StageMetrics("producer", 10000, 10000, 0, 20000),
        StageMetrics("broker", 10000, 9800, 1200, 20000),
        StageMetrics("consumer", 9800, 5200, 45000, 10000),
        StageMetrics("stateful-operator", 5200, 5100, 800, 8000),
    ]
    bottleneck = triangulate(stages)
    action = BackpressureController().recommend(
        lag=250_000, queue_depth=1_000, consumer_utilization=0.95)
    v1 = ApiContract("v1", {"id": "string", "score": "number"})
    v2 = ApiContract("v2", {"id": "string", "score": "number",
                            "severity": "string"})
    compat = check_backward_compat(v1, v2)
    summary = {
        "anomalies_found": sum(len(d.anomalies) for d in detectors),
        "correlated_signals": signals,
        "bottleneck": bottleneck,
        "backpressure": action,
        "api_v1_to_v2": compat,
        "cost_at_10_tb_per_day": cost_for_throughput(10.0),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
