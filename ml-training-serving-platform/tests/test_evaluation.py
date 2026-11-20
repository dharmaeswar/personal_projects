"""Tests for experiment tracking, the promotion gate, and retrieval eval."""

import os

from ml_platform.data import generate_applications
from ml_platform.evaluation import (
    best_experiment,
    compare_versions,
    dataset_fingerprint,
    evaluate_retrieval,
    evaluate_version,
    generate_search_corpus,
    list_experiments,
    log_experiment,
    mean_reciprocal_rank,
    precision_at_k,
    promotion_gate,
    rank_documents,
    reciprocal_rank,
)
from ml_platform.training import train


def test_log_and_list_experiments_round_trip(tmp_path):
    path = str(tmp_path / "experiments.jsonl")
    assert list_experiments(path) == []
    log_experiment(path, "baseline", {"lr": 0.1, "epochs": 300},
                   {"auc": 0.81, "accuracy": 0.74}, model_version="v1")
    log_experiment(path, "tuned", {"lr": 0.05, "epochs": 500},
                   {"auc": 0.84, "accuracy": 0.76}, model_version="v2")
    runs = list_experiments(path)
    assert len(runs) == 2
    assert runs[0]["name"] == "baseline"
    assert runs[1]["metrics"]["auc"] == 0.84
    assert runs[1]["model_version"] == "v2"


def test_best_experiment_picks_highest_auc(tmp_path):
    path = str(tmp_path / "experiments.jsonl")
    log_experiment(path, "a", {}, {"auc": 0.80})
    log_experiment(path, "b", {}, {"auc": 0.86})
    log_experiment(path, "c", {}, {"auc": 0.82})
    assert best_experiment(path, "auc")["name"] == "b"
    assert best_experiment(path, "missing") is None
    assert best_experiment(str(tmp_path / "nope.jsonl")) is None


def test_compare_versions_promotes_on_improvement():
    verdict = compare_versions(
        {"auc": 0.85, "accuracy": 0.78, "recall": 0.60},
        {"auc": 0.82, "accuracy": 0.76, "recall": 0.58},
        primary="auc", min_improvement=0.01,
        floors={"accuracy": 0.70, "recall": 0.50},
    )
    assert verdict["promote"] is True
    assert verdict["primary_delta"] == 0.03


def test_compare_versions_blocks_on_regression_and_floors():
    worse = compare_versions({"auc": 0.80}, {"auc": 0.82}, primary="auc",
                             min_improvement=0.0)
    assert worse["promote"] is False
    assert "below required" in worse["reasons"][0]
    floored = compare_versions(
        {"auc": 0.90, "accuracy": 0.65}, {"auc": 0.82, "accuracy": 0.76},
        floors={"accuracy": 0.70})
    assert floored["promote"] is False
    assert any("floor" in r for r in floored["reasons"])


def test_promotion_gate_on_real_models():
    rows = generate_applications(600, seed=99)
    train_rows, eval_rows = rows[:400], rows[400:]
    prod = train(train_rows, epochs=50, seed=1)
    cand = train(train_rows, epochs=300, seed=2)
    verdict = promotion_gate(cand, prod, eval_rows, min_improvement=0.0)
    assert verdict["candidate"]["n"] == 200
    assert verdict["production"]["n"] == 200
    assert verdict["dataset_fingerprint"] == dataset_fingerprint(eval_rows)
    assert set(verdict["candidate"]) >= {"accuracy", "precision", "recall", "auc"}


def test_evaluate_version_metrics_shape():
    rows = generate_applications(300, seed=5)
    model = train(rows[:200], epochs=50, seed=3)
    metrics = evaluate_version(model, rows[200:])
    assert metrics["n"] == 100
    assert 0.0 <= metrics["auc"] <= 1.0


def test_ranker_puts_exact_match_first():
    docs, queries = generate_search_corpus(seed=11)
    ranked = rank_documents("model drift", docs)
    assert ranked[0] == "doc-01"
    ranked = rank_documents("llm evaluation", docs)
    assert ranked[0] == "doc-04"


def test_precision_at_k_and_reciprocal_rank():
    ranked = ["a", "b", "c", "d"]
    assert precision_at_k(ranked, ["a", "c"], 2) == 0.5
    assert precision_at_k(ranked, ["a", "c"], 4) == 0.5
    assert precision_at_k(ranked, [], 2) == 0.0
    assert precision_at_k([], ["a"], 2) == 0.0
    assert reciprocal_rank(ranked, ["c"]) == round(1 / 3, 4)
    assert reciprocal_rank(ranked, ["z"]) == 0.0


def test_mean_reciprocal_rank_perfect_and_partial():
    docs = [
        {"id": "x", "title": "alpha guide", "text": "alpha alpha"},
        {"id": "y", "title": "beta guide", "text": "beta beta"},
    ]
    assert mean_reciprocal_rank([("alpha", ["x"]), ("beta", ["y"])], docs) == 1.0
    assert mean_reciprocal_rank([("alpha", ["y"])], docs) == 0.5
    assert mean_reciprocal_rank([], docs) == 0.0


def test_evaluate_retrieval_on_synthetic_corpus():
    docs, queries = generate_search_corpus(seed=11)
    result = evaluate_retrieval(docs, queries, k=3)
    assert result["n_queries"] == 6
    assert result["mrr"] == 1.0  # each query's doc matches its own title terms
    assert result["precision_at_3"] >= 0.33
