"""Autonomy evaluation & metrics platform service.

Ties the registry, run ledger, metric computer, comparison tools, and
regression gates into one service — the shape of Rivian's Autonomy Eval
Infrastructure team: register versioned metrics, record eval runs with
full provenance, compute metrics idempotently, compare model versions with
uncertainty shown, and gate releases on the evidence. A CI hook runs the
gates for a candidate model version and returns a pass/fail verdict the
pipeline can act on.
"""

from __future__ import annotations

from .compare import Comparison, classify_failure, compare_rates
from .compute import MetricComputer
from .gates import Gate, build_release_evidence
from .provenance import EvalRun, RunLedger
from .registry import MetricRegistry


class EvalMetricsPlatform:
    def __init__(self):
        self.registry = MetricRegistry()
        self.ledger = RunLedger()
        self.computer = MetricComputer()
        self._gates: list[Gate] = []

    # -- metrics -------------------------------------------------------
    def register_metric(self, name: str, description: str, unit: str,
                        aggregation: str, slice_dims=(), higher_is_better=True):
        return self.registry.register(name, description, unit, aggregation,
                                      slice_dims, higher_is_better)

    def add_gate(self, gate: Gate) -> None:
        self._gates.append(gate)

    # -- runs ----------------------------------------------------------
    def record_run(self, run: EvalRun) -> EvalRun:
        return self.ledger.record(run)

    def compute_metric(self, run_id: str, metric_name: str, slice_key: str,
                       values: list[float], expected_scenarios: int,
                       backfill_id: str | None = None):
        run = self.ledger.get(run_id)
        if run is None:
            raise ValueError(f"unknown run {run_id!r}")
        definition = self.registry.get(metric_name, run.metric_version)
        if definition is None:
            raise ValueError(f"no metric {metric_name} v{run.metric_version}")
        return self.computer.compute(run_id, metric_name, run.metric_version,
                                     slice_key, values, definition.aggregation,
                                     expected_scenarios, backfill_id)

    # -- compare + gate -------------------------------------------------
    def compare_models(self, metric_name: str, baseline_successes: int,
                       baseline_n: int, candidate_successes: int,
                       candidate_n: int, baseline_coverage: float = 1.0,
                       candidate_coverage: float = 1.0) -> Comparison:
        definition = self.registry.latest(metric_name)
        if definition is None:
            raise ValueError(f"unknown metric {metric_name!r}")
        return compare_rates(baseline_successes, baseline_n, candidate_successes,
                             candidate_n, metric_name, definition.higher_is_better,
                             baseline_coverage, candidate_coverage)

    def ci_check(self, model_version: str, comparisons: dict[str, Comparison]) -> dict:
        """CI hook: run the gates for a candidate model version."""
        evidence = build_release_evidence(model_version, self._gates, comparisons)
        return evidence.summary()

    def diagnose(self, **kwargs) -> str:
        return classify_failure(**kwargs)
