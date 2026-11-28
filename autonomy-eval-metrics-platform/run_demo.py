"""End-to-end demo: two model versions evaluated on simulation + real-world data.

Registers an intervention-rate metric, records eval runs with provenance,
computes the metric idempotently, compares the candidate model against the
baseline with confidence intervals, diagnoses a coverage drop on one slice,
and runs the release gates through the CI hook.
"""

from eval_platform import EvalMetricsPlatform
from eval_platform.gates import Gate
from eval_platform.provenance import EvalRun
from eval_platform.workcell import (
    publish_workcell_metrics,
    simulate_workcell_cycles,
    workcell_metrics,
)


def main():
    platform = EvalMetricsPlatform()
    platform.register_metric(
        "intervention_rate", "Safety-critical interventions per scenario",
        "rate", "rate", slice_dims=("road_type",), higher_is_better=False)
    platform.register_metric(
        "mission_completion", "Share of missions completed without disengagement",
        "rate", "rate", slice_dims=("road_type",), higher_is_better=True)
    platform.add_gate(Gate("intervention_rate", max_regression=0.005,
                           higher_is_better=False))
    platform.add_gate(Gate("mission_completion", min_value=0.95,
                           higher_is_better=True))

    baseline = EvalRun("run-base-001", "intervention_rate", 1, "code-a1b2",
                       "model-2026.10", "dataset-2026.10", "scenarios-v12",
                       "simulation")
    candidate = EvalRun("run-cand-001", "intervention_rate", 1, "code-c3d4",
                        "model-2026.11", "dataset-2026.10", "scenarios-v12",
                        "simulation")
    platform.record_run(baseline)
    platform.record_run(candidate)

    # 1,000 simulated scenarios each; interventions are rare events.
    base_values = [1.0] * 40 + [0.0] * 960
    cand_values = [1.0] * 12 + [0.0] * 988
    r1 = platform.compute_metric("run-base-001", "intervention_rate", "highway",
                                 base_values, expected_scenarios=1000)
    r2 = platform.compute_metric("run-cand-001", "intervention_rate", "highway",
                                 cand_values, expected_scenarios=1000)
    # Idempotent retry: same inputs, same stored result.
    r2_again = platform.compute_metric("run-cand-001", "intervention_rate", "highway",
                                       cand_values, expected_scenarios=1000)
    print("baseline:", r1)
    print("candidate:", r2)
    print("idempotent retry returns same object:", r2 is r2_again)

    comparison = platform.compare_models("intervention_rate", 40, 1000, 12, 1000)
    print("\ncomparison:", comparison)

    mission = platform.compare_models("mission_completion", 962, 1000, 985, 1000)
    print("mission completion:", mission)

    print("\nCI gate check:")
    print(platform.ci_check("model-2026.11", {
        "intervention_rate": comparison, "mission_completion": mission}))

    print("\ndiagnosis (coverage drop on a slice):")
    print(platform.diagnose(coverage=0.62, missing_inputs=140, failed_jobs=0,
                            total_jobs=40, metric_changed=True))
    print(platform.diagnose(coverage=1.0, missing_inputs=0, failed_jobs=0,
                            total_jobs=40, metric_changed=True))

    print("\nworkcell simulation (500 pick-and-place cycles):")
    cycles = simulate_workcell_cycles(seed=7, n_cycles=500)
    published = publish_workcell_metrics(platform, "run-wc-001", cycles)
    for name, result in published.items():
        print(f"  {name}: {result.value} (coverage {result.coverage})")
    print("  effectiveness summary:", workcell_metrics(cycles))


if __name__ == "__main__":
    main()
