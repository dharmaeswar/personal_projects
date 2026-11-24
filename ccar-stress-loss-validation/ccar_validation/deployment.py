"""Model deployment pipeline and execution platform for the stress-loss models.

Covers the deployment & platform side of a credit-risk modelling team: a
staged execution pipeline (ingest -> score -> validate -> publish), a
versioned model registry with champion / challenger promotion gates, and
execution monitoring (stage timings, row counts, failure reasons).

All data is synthetic and seeded; nothing here is a real filing or a claim
about any real institution's models.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

PIPELINE_STAGES = ("ingest", "score", "validate", "publish")


@dataclass
class StageResult:
    stage: str
    status: str  # "pass" or "fail"
    seconds: float
    rows: int
    detail: str = ""


@dataclass
class PipelineRun:
    model_name: str
    model_version: str
    stages: list[StageResult] = field(default_factory=list)
    published: bool = False

    @property
    def status(self) -> str:
        return "pass" if self.stages and all(s.status == "pass" for s in self.stages) else "fail"

    @property
    def total_seconds(self) -> float:
        return sum(s.seconds for s in self.stages)


def score_batch(model, df: pd.DataFrame) -> np.ndarray:
    """Score a batch of loans and reject invalid output.

    Loss-rate forecasts must be finite and inside [0, 1]; anything else is a
    pipeline failure, not a number to publish.
    """
    scores = np.asarray(model.predict(df), dtype=float)
    if scores.shape[0] != len(df):
        raise ValueError(f"scored {scores.shape[0]} rows for {len(df)} input rows")
    if not np.isfinite(scores).all():
        raise ValueError("non-finite scores in batch")
    if scores.min() < 0.0 or scores.max() > 1.0:
        raise ValueError(f"scores outside [0, 1]: min={scores.min():.4f} max={scores.max():.4f}")
    return scores


def validate_scores(scores: np.ndarray, reference: np.ndarray, max_mae: float = 0.20) -> tuple[bool, str]:
    """Post-scoring validation gate: the batch must look sane against reference.

    Fails when the batch MAE against realised loss rates is far above the
    level the backtest showed, which means the deployed model or its inputs
    have drifted since validation.
    """
    mae = float(np.mean(np.abs(scores - reference)))
    if mae > max_mae:
        return False, f"batch MAE {mae:.4f} above gate {max_mae:.2f}"
    return True, f"batch MAE {mae:.4f} within gate {max_mae:.2f}"


def run_pipeline(model, df: pd.DataFrame, reference: np.ndarray, model_name: str,
                 model_version: str) -> PipelineRun:
    """Run the four-stage deployment pipeline for one model version.

    Publish happens only when ingest, scoring and validation all pass, so a
    broken model version can never reach the published registry.
    """
    run = PipelineRun(model_name=model_name, model_version=model_version)

    # 1. Ingest: the batch must have the features the model was fitted on.
    t0 = time.perf_counter()
    required = {"gdp_growth", "unemployment_rate", "hpi_growth", "credit_spread", "ltv", "fico_score"}
    missing = required - set(df.columns)
    run.stages.append(StageResult(
        "ingest",
        "fail" if missing else "pass",
        time.perf_counter() - t0,
        len(df),
        f"missing columns: {sorted(missing)}" if missing else f"{len(df)} rows, all features present",
    ))
    if missing:
        return run

    # 2. Score.
    t0 = time.perf_counter()
    try:
        scores = score_batch(model, df)
        run.stages.append(StageResult("score", "pass", time.perf_counter() - t0, len(df),
                                       f"{len(scores)} scores in [0, 1]"))
    except ValueError as exc:
        run.stages.append(StageResult("score", "fail", time.perf_counter() - t0, len(df), str(exc)))
        return run

    # 3. Validate against realised loss rates.
    t0 = time.perf_counter()
    ok, detail = validate_scores(scores, reference)
    run.stages.append(StageResult("validate", "pass" if ok else "fail",
                                  time.perf_counter() - t0, len(df), detail))
    if not ok:
        return run

    # 4. Publish.
    t0 = time.perf_counter()
    run.stages.append(StageResult("publish", "pass", time.perf_counter() - t0, len(df),
                                  f"{model_name} v{model_version} published"))
    run.published = True
    return run


def promotion_gate(champion: dict, challenger: dict, mae_improvement: float = 0.02,
                   max_hit_rate_drop: float = 0.01) -> tuple[bool, list[str]]:
    """Champion / challenger promotion gate.

    The challenger promotes only when it beats the champion's MAE by at
    least `mae_improvement` (relative) without losing more than
    `max_hit_rate_drop` of hit rate. Returns (promote, reasons).
    """
    reasons = []
    mae_gain = (champion["mae"] - challenger["mae"]) / champion["mae"] if champion["mae"] else 0.0
    hit_drop = champion["hit_rate"] - challenger["hit_rate"]
    promote = True
    if mae_gain < mae_improvement:
        reasons.append(f"MAE gain {mae_gain:.1%} below required {mae_improvement:.0%}")
        promote = False
    if hit_drop > max_hit_rate_drop:
        reasons.append(f"hit rate drop {hit_drop:.3f} above allowed {max_hit_rate_drop:.3f}")
        promote = False
    if promote:
        reasons.append(f"MAE gain {mae_gain:.1%}, hit rate change {(-hit_drop):+.3f}: promote")
    return promote, reasons


class ModelRegistry:
    """Versioned registry of deployed model versions.

    Each version records its backtest metrics and a status. Only one version
    per model name is the champion at a time; promotion goes through
    `promotion_gate`, never by hand.
    """

    def __init__(self) -> None:
        self.versions: dict[str, dict] = {}

    def register(self, name: str, version: str, metrics: dict, status: str = "challenger") -> None:
        key = f"{name} v{version}"
        if key in self.versions:
            raise ValueError(f"{key} already registered")
        self.versions[key] = {"name": name, "version": version,
                              "mae": metrics["mae"], "hit_rate": metrics["hit_rate"],
                              "status": status}

    def champion(self, name: str) -> dict | None:
        for entry in self.versions.values():
            if entry["name"] == name and entry["status"] == "champion":
                return entry
        return None

    def promote(self, name: str, version: str, gate_passed: bool) -> str:
        """Promote a challenger to champion, demoting the old champion."""
        if not gate_passed:
            return f"{name} v{version}: promotion blocked by gate"
        key = f"{name} v{version}"
        if key not in self.versions:
            raise ValueError(f"{key} is not registered")
        old = self.champion(name)
        if old is not None:
            old["status"] = "retired"
        self.versions[key]["status"] = "champion"
        return f"{name} v{version}: promoted to champion"


def build_deployment_section(run: PipelineRun, registry: ModelRegistry,
                             gate: tuple[bool, list[str]]) -> str:
    """Plain-text report section for the deployment pipeline run."""
    lines = []
    lines.append("10. MODEL DEPLOYMENT PIPELINE (EXECUTION PLATFORM)")
    lines.append(f"   Model: {run.model_name} v{run.model_version}  overall: {run.status.upper()}  "
                 f"published: {'yes' if run.published else 'no'}  "
                 f"total time: {run.total_seconds:.2f}s")
    for stage in run.stages:
        lines.append(f"   {stage.stage:9s} {stage.status:4s}  {stage.seconds:6.2f}s  "
                     f"rows={stage.rows}  {stage.detail}")
    lines.append("")
    lines.append("   MODEL REGISTRY")
    for key, entry in sorted(registry.versions.items()):
        lines.append(f"   {key:28s} {entry['status']:10s}  MAE={entry['mae']:.4f}  "
                     f"hit_rate={entry['hit_rate']:.3f}")
    lines.append("")
    lines.append("   CHAMPION / CHALLENGER PROMOTION GATE")
    lines.append(f"   promote challenger: {'YES' if gate[0] else 'NO'}")
    for reason in gate[1]:
        lines.append(f"   - {reason}")
    return "\n".join(lines)
