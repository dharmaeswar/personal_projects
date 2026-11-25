from sdlc_agents.benchmarks import (
    BenchmarkTask, SuiteResult, TaskScore, ab_compare, grade,
    pareto_frontier, run_suite,
)


def test_bug_detection_full_marks_when_bug_named():
    task = BenchmarkTask("b1", "bug_detection", "find bug", "off-by-one divide count")
    assert grade(task, "the bug is an off-by-one divide count error", 100).score == 1.0


def test_bug_detection_partial_credit():
    task = BenchmarkTask("b1", "bug_detection", "find bug", "off-by-one divide count")
    score = grade(task, "off-by-one error", 100).score
    assert 0.0 < score < 1.0


def test_review_quality_scores_term_overlap():
    task = BenchmarkTask("r1", "review_quality", "review", "negative amount validation error")
    assert grade(task, "negative amount validation error", 100).score == 1.0
    assert grade(task, "looks fine", 100).score == 0.0


def test_latency_within_budget_scores_full():
    task = BenchmarkTask("l1", "latency", "summarize", "fast", max_latency_ms=1000)
    assert grade(task, "x", 500).score == 1.0
    assert grade(task, "x", 2000).score == 0.0
    assert grade(task, "x", 1500).score == 0.5


def test_suite_mean_and_pass_rate():
    result = SuiteResult(scores=[
        TaskScore("a", "bug_detection", 1.0, 10, ""),
        TaskScore("b", "bug_detection", 0.5, 10, ""),
    ])
    assert result.mean() == 0.75
    assert result.pass_rate() == 0.5
    assert result.mean_by_kind() == {"bug_detection": 0.75}


def test_run_suite_uses_answer_fn():
    tasks = [BenchmarkTask("b1", "bug_detection", "p", "off-by-one divide count")]
    result = run_suite(tasks, lambda t: (t.expected, 50.0))
    assert result.mean() == 1.0


def test_ab_compare_verdicts():
    base = SuiteResult([TaskScore("a", "bug_detection", 0.5, 1, "")])
    better = SuiteResult([TaskScore("a", "bug_detection", 0.9, 1, "")])
    worse = SuiteResult([TaskScore("a", "bug_detection", 0.2, 1, "")])
    assert ab_compare(base, better)["verdict"] == "candidate wins"
    assert ab_compare(base, worse)["verdict"] == "candidate loses"
    assert ab_compare(base, base)["verdict"] == "no meaningful change"


def test_pareto_frontier_drops_dominated_points():
    points = [(0.02, 0.55), (0.10, 0.82), (0.35, 0.93), (0.40, 0.88), (0.12, 0.78)]
    frontier = pareto_frontier(points)
    assert (0.40, 0.88) not in frontier  # dominated by (0.35, 0.93): cheaper and better
    assert (0.12, 0.78) not in frontier  # dominated by (0.10, 0.82)
    assert frontier == [(0.02, 0.55), (0.10, 0.82), (0.35, 0.93)]
