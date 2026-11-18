"""Evaluation: all strategies run, metrics bounded, results deterministic."""

from rag_evaluator.evaluate import format_report, run_evaluation


def test_all_strategies_evaluated():
    results = run_evaluation()
    assert set(results) == {"fixed", "sentence", "sliding"}
    for data in results.values():
        assert data["chunks"] > 0
        assert len(data["per_query"]) == 6


def test_metrics_between_zero_and_one():
    results = run_evaluation()
    for data in results.values():
        assert 0.0 <= data["mean_precision@3"] <= 1.0
        assert 0.0 <= data["mean_recall@3"] <= 1.0
        for row in data["per_query"]:
            assert 0.0 <= row["precision"] <= 1.0
            assert 0.0 <= row["recall"] <= 1.0


def test_evaluation_is_deterministic():
    assert run_evaluation() == run_evaluation()


def test_every_query_retrieves_something_relevant_for_some_strategy():
    results = run_evaluation()
    for query_id in ("q1", "q2", "q3", "q4", "q5", "q6"):
        assert any(
            row["recall"] > 0
            for data in results.values()
            for row in data["per_query"]
            if row["query"] == query_id
        ), query_id


def test_report_names_a_best_strategy():
    results = run_evaluation()
    report = format_report(results)
    assert "Best mean recall@3:" in report
    for strategy in ("fixed", "sentence", "sliding"):
        assert strategy in report
