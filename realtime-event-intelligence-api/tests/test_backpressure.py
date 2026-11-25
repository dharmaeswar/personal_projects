"""Tests for backpressure, bottleneck triangulation, and cost modelling."""

import pytest

from event_intel.backpressure import (BackpressureController, StageMetrics,
                                      cost_for_throughput, triangulate)


def stages():
    return [
        StageMetrics("producer", 10000, 10000, 0, 20000),
        StageMetrics("broker", 10000, 9800, 1200, 20000),
        StageMetrics("consumer", 9800, 5200, 45000, 10000),
        StageMetrics("stateful-operator", 5200, 5100, 800, 8000),
    ]


def test_triangulate_names_slowest_stage():
    result = triangulate(stages())
    assert result["bottleneck"] == "consumer"
    assert result["ranking"][0] == "consumer"
    assert result["drain_ratio"] < 1.0
    assert "consumer" in result["evidence"]


def test_triangulate_needs_stages():
    with pytest.raises(ValueError):
        triangulate([])


def test_backpressure_shed_load_at_high_lag():
    controller = BackpressureController()
    rec = controller.recommend(lag=2_000_000, queue_depth=60_000,
                               consumer_utilization=0.95)
    assert rec["action"] == "shed_load"


def test_backpressure_scale_consumers_when_saturated():
    controller = BackpressureController()
    rec = controller.recommend(lag=250_000, queue_depth=1_000,
                               consumer_utilization=0.95)
    assert rec["action"] == "scale_consumers"


def test_backpressure_tune_when_headroom():
    controller = BackpressureController()
    rec = controller.recommend(lag=250_000, queue_depth=1_000,
                               consumer_utilization=0.5)
    assert rec["action"] == "tune_consumer"


def test_backpressure_none_when_healthy():
    controller = BackpressureController()
    rec = controller.recommend(lag=500, queue_depth=100,
                               consumer_utilization=0.4)
    assert rec["action"] == "none"


def test_cost_model_splits_and_dominance():
    cost = cost_for_throughput(10.0)
    assert cost["tb_per_day"] == 10.0
    assert cost["total_usd_per_day"] == round(
        cost["ingest_usd_per_day"] + cost["retention_usd_per_day"]
        + cost["scan_usd_per_day"], 2)
    assert cost["dominant"] == "retention"  # 7-day retention dominates


def test_cost_model_rejects_negative():
    with pytest.raises(ValueError):
        cost_for_throughput(-1.0)
