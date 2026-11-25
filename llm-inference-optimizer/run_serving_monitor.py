"""Demo: monitor a serving deployment after it ships.

Checks a synthetic latency window against an SLO, compares production
outputs with the research reference, and triages the mismatch that
shows up — the post-deployment half of the inference-optimizer toolkit.

Run from the project directory:
    python3 run_serving_monitor.py
"""

from inference_optimizer.serving_monitor import (
    LatencySLO,
    ServingSnapshot,
    check_latency,
    compare_outputs,
    investigate_discrepancy,
)


def main():
    slo = LatencySLO(p50_ms=20.0, p95_ms=40.0, p99_ms=80.0)
    latencies = [12.0, 14.0, 15.0, 18.0, 21.0, 26.0, 33.0, 47.0]
    report = check_latency(latencies, slo)
    print(f"Latency window ({report.samples} samples): p50 {report.p50_ms} ms, "
          f"p95 {report.p95_ms} ms, p99 {report.p99_ms} ms — "
          f"{'SLO met' if report.passes else 'SLO breached: ' + ', '.join(report.breaches)} "
          f"(bottleneck: {report.bottleneck})")

    snapshot = ServingSnapshot(
        gpu_memory_used_gb=62.0, gpu_memory_total_gb=80.0,
        gpu_utilization=0.72, throughput_tokens_per_sec=1450.0,
        error_rate=0.002, latency=report,
    )
    health = snapshot.health()
    print(f"Serving health: {health['verdict']} — "
          f"memory pressure {snapshot.memory_pressure:.0%}, "
          f"{'; '.join(health['reasons']) or 'no issues'}")

    # Production outputs vs the research reference for the same inputs.
    # The deployment serves in INT8 while research ran in fp16.
    reference = [0.84, 1.27, -0.42, 2.05, 0.31, 1.88]
    production = [0.85, 1.26, -0.41, 2.11, 0.32, 1.87]
    comparison = compare_outputs(reference, production, tolerance=0.05)
    print(f"Output comparison: max diff {comparison.max_abs_diff}, "
          f"{comparison.over_tolerance}/{comparison.compared} over tolerance "
          f"(worst at index {comparison.worst_index})")
    for finding in investigate_discrepancy(comparison, dtype_changed=True):
        print(f"  triage: {finding.cause} ({finding.likelihood}) — {finding.check}")


if __name__ == "__main__":
    main()
