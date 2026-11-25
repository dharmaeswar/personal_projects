"""Benchmark suites graded on real-world tasks, plus A/B and Pareto tracking.

Benchmarks are the empirical check on agent improvements: bug detection,
review quality and latency, each graded against a known expected answer —
not by intuition. An A/B comparison says whether a change really helped;
a Pareto frontier says which (cost, quality) tradeoffs are worth keeping.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BenchmarkTask:
    task_id: str
    kind: str  # bug_detection | review_quality | latency
    prompt: str
    expected: str
    max_latency_ms: float = 1000.0


@dataclass
class TaskScore:
    task_id: str
    kind: str
    score: float  # 0-1
    latency_ms: float
    detail: str


def grade(task: BenchmarkTask, answer: str, latency_ms: float) -> TaskScore:
    """Grade one answer. Bug detection and review quality are exact/keyword
    matches against the seeded expected answer; latency scores 1.0 inside
    budget and decays linearly to 0 at twice the budget."""
    if task.kind == "latency":
        if latency_ms <= task.max_latency_ms:
            score, detail = 1.0, "within latency budget"
        elif latency_ms >= 2 * task.max_latency_ms:
            score, detail = 0.0, "over twice the latency budget"
        else:
            score = 1.0 - (latency_ms - task.max_latency_ms) / task.max_latency_ms
            detail = "partially over latency budget"
        return TaskScore(task.task_id, task.kind, round(score, 3), latency_ms, detail)
    expected_terms = {w.lower() for w in task.expected.split() if len(w) > 2}
    answer_terms = {w.lower().strip(".,:;") for w in answer.split()}
    hit = len(expected_terms & answer_terms) / len(expected_terms) if expected_terms else 0.0
    if task.kind == "bug_detection":
        score = 1.0 if hit >= 0.8 else round(hit, 3)
        detail = "bug named" if score == 1.0 else f"matched {hit:.0%} of expected terms"
    else:  # review_quality
        score = round(hit, 3)
        detail = f"matched {hit:.0%} of expected review points"
    return TaskScore(task.task_id, task.kind, score, latency_ms, detail)


@dataclass
class SuiteResult:
    scores: list[TaskScore] = field(default_factory=list)

    def mean(self) -> float:
        return round(sum(s.score for s in self.scores) / len(self.scores), 3) if self.scores else 0.0

    def mean_by_kind(self) -> dict[str, float]:
        kinds: dict[str, list[float]] = {}
        for s in self.scores:
            kinds.setdefault(s.kind, []).append(s.score)
        return {k: round(sum(v) / len(v), 3) for k, v in sorted(kinds.items())}

    def pass_rate(self, threshold: float = 0.8) -> float:
        if not self.scores:
            return 0.0
        return round(sum(1 for s in self.scores if s.score >= threshold) / len(self.scores), 3)


def run_suite(tasks: list[BenchmarkTask], answer_fn) -> SuiteResult:
    """Run every task through answer_fn(task) -> (answer, latency_ms)."""
    result = SuiteResult()
    for task in tasks:
        answer, latency_ms = answer_fn(task)
        result.scores.append(grade(task, answer, latency_ms))
    return result


def ab_compare(baseline: SuiteResult, candidate: SuiteResult) -> dict:
    """Compare two suite runs: overall and per-kind mean deltas, verdict."""
    delta = round(candidate.mean() - baseline.mean(), 3)
    kinds = sorted({*baseline.mean_by_kind(), *candidate.mean_by_kind()})
    per_kind = {
        k: round(candidate.mean_by_kind().get(k, 0.0) - baseline.mean_by_kind().get(k, 0.0), 3)
        for k in kinds
    }
    if delta >= 0.05:
        verdict = "candidate wins"
    elif delta <= -0.05:
        verdict = "candidate loses"
    else:
        verdict = "no meaningful change"
    return {"delta": delta, "per_kind_delta": per_kind, "verdict": verdict}


def pareto_frontier(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Non-dominated (cost, quality) points: keep a point only if no other
    point is both cheaper (or equal) and better (or equal). Lower cost and
    higher quality are both better."""
    frontier: list[tuple[float, float]] = []
    for cost, quality in points:
        dominated = any(
            (c <= cost and q >= quality) and (c < cost or q > quality)
            for c, q in points
        )
        if not dominated:
            frontier.append((cost, quality))
    return sorted(frontier)
