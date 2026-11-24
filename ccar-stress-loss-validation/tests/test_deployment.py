"""Tests for the model deployment pipeline and registry."""

import numpy as np
import pandas as pd
import pytest

from ccar_validation.backtest import backtest_all
from ccar_validation.data import generate_portfolio, train_test_split
from ccar_validation.deployment import (
    ModelRegistry,
    PipelineRun,
    build_deployment_section,
    promotion_gate,
    run_pipeline,
    score_batch,
    validate_scores,
)
from ccar_validation.models import fit_all


@pytest.fixture(scope="module")
def fitted():
    portfolio = generate_portfolio()
    train, test = train_test_split(portfolio)
    return fit_all(train), train, test


def test_score_batch_returns_valid_loss_rates(fitted):
    models, _, test = fitted
    scores = score_batch(models["champion"], test)
    assert len(scores) == len(test)
    assert np.isfinite(scores).all()
    assert scores.min() >= 0.0 and scores.max() <= 1.0


def test_validate_scores_passes_on_real_backtest(fitted):
    models, _, test = fitted
    scores = score_batch(models["champion"], test)
    ok, detail = validate_scores(scores, test["observed_loss_rate"].to_numpy())
    assert ok
    assert "MAE" in detail


def test_validate_scores_fails_on_garbage():
    scores = np.full(50, 0.9)
    reference = np.zeros(50)
    ok, detail = validate_scores(scores, reference)
    assert not ok
    assert "above gate" in detail


def test_pipeline_passes_end_to_end(fitted):
    models, _, test = fitted
    run = run_pipeline(models["champion"], test, test["observed_loss_rate"].to_numpy(),
                       "stress-loss-forecaster", "1.0")
    assert run.status == "pass"
    assert run.published is True
    assert [s.stage for s in run.stages] == ["ingest", "score", "validate", "publish"]
    assert all(s.status == "pass" for s in run.stages)
    assert run.total_seconds >= 0.0


def test_pipeline_fails_on_missing_feature(fitted):
    models, _, test = fitted
    bad = test.drop(columns=["fico_score"])
    run = run_pipeline(models["champion"], bad, test["observed_loss_rate"].to_numpy(),
                       "stress-loss-forecaster", "1.0")
    assert run.status == "fail"
    assert run.published is False
    assert run.stages[0].stage == "ingest" and run.stages[0].status == "fail"
    assert len(run.stages) == 1  # stops before scoring


def test_pipeline_fails_on_bad_reference(fitted):
    models, _, test = fitted
    wrong_reference = np.ones(len(test))
    run = run_pipeline(models["champion"], test, wrong_reference,
                       "stress-loss-forecaster", "1.0")
    assert run.status == "fail"
    assert run.published is False
    assert run.stages[-1].stage == "validate"


def test_promotion_gate_blocks_weaker_challenger():
    champion = {"mae": 0.05, "hit_rate": 0.90}
    challenger = {"mae": 0.06, "hit_rate": 0.85}
    promote, reasons = promotion_gate(champion, challenger)
    assert promote is False
    assert len(reasons) == 2


def test_promotion_gate_passes_clearly_better_challenger():
    champion = {"mae": 0.05, "hit_rate": 0.90}
    challenger = {"mae": 0.04, "hit_rate": 0.905}
    promote, reasons = promotion_gate(champion, challenger)
    assert promote is True
    assert "promote" in reasons[0]


def test_registry_promote_demotes_old_champion():
    registry = ModelRegistry()
    registry.register("loss-forecaster", "1.0", {"mae": 0.05, "hit_rate": 0.90}, status="champion")
    registry.register("loss-forecaster", "2.0", {"mae": 0.04, "hit_rate": 0.91})
    assert registry.champion("loss-forecaster")["version"] == "1.0"
    msg = registry.promote("loss-forecaster", "2.0", gate_passed=True)
    assert "promoted to champion" in msg
    assert registry.champion("loss-forecaster")["version"] == "2.0"
    assert registry.versions["loss-forecaster v1.0"]["status"] == "retired"


def test_registry_blocks_promotion_when_gate_fails():
    registry = ModelRegistry()
    registry.register("loss-forecaster", "1.0", {"mae": 0.05, "hit_rate": 0.90}, status="champion")
    registry.register("loss-forecaster", "2.0", {"mae": 0.06, "hit_rate": 0.85})
    msg = registry.promote("loss-forecaster", "2.0", gate_passed=False)
    assert "blocked by gate" in msg
    assert registry.champion("loss-forecaster")["version"] == "1.0"


def test_registry_rejects_duplicate_version():
    registry = ModelRegistry()
    registry.register("loss-forecaster", "1.0", {"mae": 0.05, "hit_rate": 0.90})
    with pytest.raises(ValueError):
        registry.register("loss-forecaster", "1.0", {"mae": 0.05, "hit_rate": 0.90})


def test_deployment_section_text(fitted):
    models, _, test = fitted
    run = run_pipeline(models["champion"], test, test["observed_loss_rate"].to_numpy(),
                       "stress-loss-forecaster", "1.0")
    registry = ModelRegistry()
    registry.register("stress-loss-forecaster", "1.0",
                      {"mae": 0.05, "hit_rate": 0.90}, status="champion")
    section = build_deployment_section(run, registry, (False, ["MAE gain 0.0% below required 2%"]))
    assert "MODEL DEPLOYMENT PIPELINE" in section
    assert "MODEL REGISTRY" in section
    assert "PROMOTION GATE" in section
    assert "published: yes" in section
