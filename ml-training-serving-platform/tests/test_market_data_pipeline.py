"""Tests for the market-data pipeline: ingestion, featurization, time split,
training, baselines, and the promotion gate. All data is synthetic/seeded.
"""
import math

import pytest

from ml_platform.evaluation import dataset_fingerprint, promotion_gate
from ml_platform.market_data_pipeline import (
    MARKET_FEATURES,
    MarketModel,
    baseline_metrics,
    featurize,
    generate_order_events,
    run_market_pipeline,
    time_split,
    train_market_model,
)
from ml_platform.eval_pipeline import reproducibility_manifest


def test_events_deterministic_and_ordered():
    a = generate_order_events(500, seed=3)
    b = generate_order_events(500, seed=3)
    assert a == b
    assert len(a) == 500
    assert all(a[i]["ts_ms"] < a[i + 1]["ts_ms"] for i in range(len(a) - 1))
    assert all(e["side"] in ("bid", "ask") for e in a)
    assert all(e["kind"] in ("add", "cancel", "trade") for e in a)
    assert all(e["size"] > 0 and e["mid"] > 0 for e in a)


def test_features_bounded_and_sane():
    events = generate_order_events(1000, seed=5)
    rows = featurize(events, window=50, horizon=10, stride=10)
    assert rows
    for feats, label, ts in rows:
        assert set(feats) == set(MARKET_FEATURES)
        assert -1.0 <= feats["order_flow_imbalance"] <= 1.0
        assert feats["realized_vol"] >= 0.0
        assert 0.0 <= feats["trade_share"] <= 1.0
        assert 0.0 <= feats["cancel_ratio"] <= 1.0
        assert label in (0, 1)


def test_label_uses_future_only():
    # Build a stream where the mid jumps up only after a known index; rows
    # whose window ends before the jump must not see it in their features,
    # and rows straddling the jump must label on the future move.
    events = generate_order_events(300, seed=9)
    rows = featurize(events, window=20, horizon=5, stride=5)
    # Recompute one label by hand from the raw events.
    feats, label, ts = rows[3]
    i = 19 + 3 * 5  # window=20, stride=5 -> row 3 ends at event index 34
    assert events[i]["ts_ms"] == ts
    assert label == (1 if events[i + 5]["mid"] > events[i]["mid"] else 0)


def test_time_split_never_mixes_order():
    events = generate_order_events(2000, seed=11)
    rows = featurize(events, window=50, horizon=10, stride=10)
    train_rows, test_rows = time_split(rows)
    assert train_rows and test_rows
    assert train_rows[-1][2] < test_rows[0][2]
    assert len(train_rows) + len(test_rows) == len(rows)
    with pytest.raises(ValueError):
        time_split(list(reversed(rows)))


def test_model_beats_naive_baselines():
    events = generate_order_events(20000, seed=42)
    rows = featurize(events, window=50, horizon=10, stride=10)
    train_rows, test_rows = time_split(rows)
    model = train_market_model(train_rows, epochs=300, seed=7)
    eval_rows = [(f, y) for f, y, _ in test_rows]
    from ml_platform.evaluation import evaluate

    metrics = evaluate(model, eval_rows)
    baselines = baseline_metrics(test_rows)
    assert metrics["auc"] > 0.5
    assert metrics["auc"] > baselines["ofi_rule_auc"]
    assert metrics["accuracy"] > baselines["majority_accuracy"]


def test_model_round_trip():
    model = train_market_model(
        featurize(generate_order_events(3000, seed=13), window=50, horizon=10, stride=10),
        epochs=50,
        seed=7,
    )
    restored = MarketModel.from_dict(model.to_dict())
    feats, _, _ = featurize(generate_order_events(300, seed=99), window=50, horizon=10, stride=10)[0]
    assert restored.predict_proba(feats) == pytest.approx(model.predict_proba(feats))


def test_promotion_gate_like_for_like():
    events = generate_order_events(20000, seed=42)
    rows = featurize(events, window=50, horizon=10, stride=10)
    train_rows, test_rows = time_split(rows)
    eval_rows = [(f, y) for f, y, _ in test_rows]
    candidate = train_market_model(train_rows, epochs=300, seed=7)
    production = train_market_model(train_rows, epochs=300, seed=7,
                                    features=["order_flow_imbalance"])
    gate = promotion_gate(candidate, production, eval_rows, primary="auc",
                          min_improvement=0.005, floors={"accuracy": 0.50})
    assert gate["dataset_fingerprint"] == dataset_fingerprint(eval_rows)
    assert gate["promote"] is True
    assert gate["candidate"]["auc"] > gate["production"]["auc"]


def test_manifest_fingerprint_stable():
    events = generate_order_events(5000, seed=42)
    rows = featurize(events, window=50, horizon=10, stride=10)
    _, test_rows = time_split(rows)
    eval_rows = [(f, y) for f, y, _ in test_rows]
    config = {"window": 50, "horizon": 10, "seed": 42}
    m1 = reproducibility_manifest("synthetic-order-events", eval_rows, config, 42, "v1")
    m2 = reproducibility_manifest("synthetic-order-events", eval_rows, config, 42, "v1")
    assert m1 == m2
    m3 = reproducibility_manifest("synthetic-order-events", eval_rows, dict(config, window=60), 42, "v1")
    assert m3["config_hash"] != m1["config_hash"]


def test_full_pipeline_report():
    report = run_market_pipeline(n_events=20000, epochs=300)
    assert report["n_events"] == 20000
    assert report["n_rows"] > 0
    assert report["signal_found"] is True
    assert report["gate"]["promote"] is True
    assert report["manifest"]["code_version"].startswith("ml-training-serving-platform")
    assert report["candidate_metrics"]["auc"] > report["baselines"]["ofi_rule_auc"]
