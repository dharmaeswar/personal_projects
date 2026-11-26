"""Evaluation-run provenance.

An official evaluation run is pinned to four versions: the code that ran
it, the model under test, the dataset it ran over, and the scenario set.
Two runs are comparable only when their dataset and scenario versions
match; a run whose inputs changed is a different measurement, not a
regression. Provenance is what turns "the number moved" into evidence a
release team can trust.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvalRun:
    run_id: str
    metric_name: str
    metric_version: int
    code_version: str
    model_version: str
    dataset_version: str
    scenario_version: str
    source: str  # "simulation" | "closed_loop" | "real_world"
    status: str = "completed"  # completed | failed | partial

    def comparable_with(self, other: "EvalRun") -> bool:
        """Same metric version, dataset, and scenario set: a fair comparison."""
        return (
            self.metric_name == other.metric_name
            and self.metric_version == other.metric_version
            and self.dataset_version == other.dataset_version
            and self.scenario_version == other.scenario_version
        )

    def provenance_key(self) -> tuple:
        return (self.code_version, self.model_version, self.dataset_version,
                self.scenario_version)


class RunLedger:
    def __init__(self):
        self._runs: dict[str, EvalRun] = {}

    def record(self, run: EvalRun) -> EvalRun:
        if run.run_id in self._runs and self._runs[run.run_id] != run:
            raise ValueError(f"run {run.run_id!r} already recorded with different provenance")
        self._runs[run.run_id] = run
        return run

    def get(self, run_id: str) -> EvalRun | None:
        return self._runs.get(run_id)

    def runs_for_model(self, model_version: str) -> list[EvalRun]:
        return [r for r in self._runs.values() if r.model_version == model_version]

    def runs_for_metric(self, metric_name: str) -> list[EvalRun]:
        return [r for r in self._runs.values() if r.metric_name == metric_name]
