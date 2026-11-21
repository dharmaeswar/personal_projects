"""ML model launch and operate platform.

Models are registered with a version, an owner, and a launch checklist:
unit tests green, evaluation metrics recorded, a rollback plan with a
version and steps, an on-call owner plus a different backup, and a valid
deploy window. A model cannot launch until every checklist item passes.
Once launched, the platform tracks health (latency, error rate) against
SLOs and supports rollback to the previous version when health breaks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_LATENCY_MS = 500
MAX_ERROR_RATE = 0.05


@dataclass
class ModelVersion:
    """One version of one ML model, with its launch checklist."""

    model_name: str
    version: str
    owner: str
    tests_passed: bool
    eval_metrics: dict
    rollback_plan: dict
    on_call_primary: str
    on_call_backup: str
    deploy_window: str  # e.g. "09:00-17:00 ET weekdays"
    status: str = "registered"

    def launch_checklist(self) -> list:
        """Return launch blockers; empty means the model may launch."""
        problems = []
        if not self.tests_passed:
            problems.append("unit tests are not green")
        if not self.eval_metrics:
            problems.append("no evaluation metrics recorded")
        if not self.rollback_plan.get("version") or not self.rollback_plan.get("steps"):
            problems.append("rollback plan needs a version and steps")
        if not self.on_call_primary or self.on_call_primary == self.on_call_backup:
            problems.append("need a primary on-call owner different from the backup")
        if not self.deploy_window:
            problems.append("deploy window must be set")
        return problems


@dataclass
class HealthSample:
    """One health observation for a launched model."""

    model_name: str
    version: str
    latency_ms: float
    error_rate: float

    def slo_ok(self) -> bool:
        return self.latency_ms <= MAX_LATENCY_MS and self.error_rate <= MAX_ERROR_RATE


class ModelPlatform:
    """Registry of model versions, launch gates, health tracking, rollback."""

    def __init__(self) -> None:
        self._models: dict[tuple, ModelVersion] = {}
        self._live: dict[str, str] = {}  # model_name -> live version
        self.health: list[HealthSample] = []
        self.rollbacks: list[dict] = []

    def register(self, model: ModelVersion) -> None:
        key = (model.model_name, model.version)
        if key in self._models:
            raise ValueError(f"model {model.model_name} {model.version} already registered")
        self._models[key] = model

    def launch(self, model_name: str, version: str) -> dict:
        """Launch a model version if its checklist passes; else report blockers."""
        model = self._models.get((model_name, version))
        if model is None:
            return {"launched": False, "blockers": ["unknown model version"]}
        blockers = model.launch_checklist()
        if blockers:
            return {"launched": False, "blockers": blockers}
        previous = self._live.get(model_name)
        model.status = "live"
        self._live[model_name] = version
        return {"launched": True, "blockers": [], "previous_version": previous}

    def live_version(self, model_name: str) -> str | None:
        return self._live.get(model_name)

    def record_health(self, sample: HealthSample) -> bool:
        """Record a health sample; returns True when SLOs hold."""
        self.health.append(sample)
        return sample.slo_ok()

    def rollback(self, model_name: str, reason: str) -> dict:
        """Roll a live model back to its previous version, if one exists."""
        live = self._live.get(model_name)
        if live is None:
            return {"rolled_back": False, "reason": "model is not live"}
        earlier = sorted(
            v for (name, v) in self._models
            if name == model_name and v != live
        )
        if not earlier:
            return {"rolled_back": False, "reason": "no earlier version to roll back to"}
        target = earlier[-1]
        self._live[model_name] = target
        self._models[(model_name, live)].status = "rolled-back"
        self.rollbacks.append(
            {"model": model_name, "from": live, "to": target, "reason": reason}
        )
        return {"rolled_back": True, "reason": reason, "to_version": target}
