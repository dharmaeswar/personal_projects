"""Evaluation, observability and cost for the GenAI platform.

Evaluation runs seeded quality, accuracy, safety and drift cases through
the orchestration graph and reports pass rates — the regression suite
that runs in the delivery pipeline before a model or prompt change ships.
Observability aggregates the gateway metering records into latency,
token use, error rate and cost by team and use case, and recommends the
cheapest model that still passes evaluation for a use case.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .orchestration import run_graph
from .rag import KnowledgeBase

# Seeded evaluation cases: (question, expected fragment, category).
EVAL_CASES = [
    (
        "What is the leverage covenant limit for commercial loans?",
        "3.5x",
        "accuracy",
    ),
    (
        "How many approvals do commercial loans above $5 million need?",
        "two approvals",
        "accuracy",
    ),
    (
        "What needs dual authorization in treasury operations?",
        "dual authorization",
        "accuracy",
    ),
    (
        "How often are generative AI models in credit decisions validated?",
        "annual validation",
        "accuracy",
    ),
    (
        "Where must secrets live instead of code?",
        "vault",
        "safety",
    ),
    (
        "What is the cure period after a leverage covenant breach?",
        "cure period",
        "accuracy",
    ),
    (
        "What is the end-of-day liquidity reporting deadline?",
        "6pm",
        "accuracy",
    ),
    (
        "What do production data stores need at rest?",
        "encrypted",
        "safety",
    ),
]


@dataclass
class EvalResult:
    question: str
    category: str
    expected: str
    passed: bool
    answer: str
    grounded: bool


def run_evaluation(
    kb: KnowledgeBase, *, team: str = "platform-eval", use_case: str = "eval"
) -> dict:
    """Run every seeded case through the graph. Returns the report."""
    results: list[EvalResult] = []
    for question, expected, category in EVAL_CASES:
        state = run_graph(question, kb, team=team, use_case=use_case)
        passed = expected.lower() in state.answer.lower() and bool(
            state.validation.get("grounded")
        )
        results.append(
            EvalResult(
                question=question,
                category=category,
                expected=expected,
                passed=passed,
                answer=state.answer,
                grounded=bool(state.validation.get("grounded")),
            )
        )
    by_category: dict[str, dict[str, int]] = {}
    for result in results:
        bucket = by_category.setdefault(result.category, {"pass": 0, "total": 0})
        bucket["total"] += 1
        bucket["pass"] += 1 if result.passed else 0
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    return {
        "total": total,
        "passed": passed,
        "pass_rate": round(passed / total, 3) if total else 0.0,
        "by_category": by_category,
        "failures": [
            {"question": r.question, "expected": r.expected, "answer": r.answer}
            for r in results
            if not r.passed
        ],
        "results": results,
    }


@dataclass
class Observability:
    """Aggregates gateway metering records into platform metrics."""

    records: list[dict] = field(default_factory=list)

    def add(self, record: dict) -> None:
        self.records.append(record)

    def summary(self) -> dict:
        if not self.records:
            return {"calls": 0}
        total_tokens = sum(
            r["input_tokens"] + r["output_tokens"] for r in self.records
        )
        total_cost = round(sum(r["cost_usd"] for r in self.records), 6)
        avg_latency = round(
            sum(r["latency_ms_p50"] for r in self.records) / len(self.records), 1
        )
        by_team: dict[str, float] = {}
        by_use_case: dict[str, float] = {}
        by_model: dict[str, float] = {}
        for record in self.records:
            by_team[record["team"]] = round(
                by_team.get(record["team"], 0.0) + record["cost_usd"], 6
            )
            by_use_case[record["use_case"]] = round(
                by_use_case.get(record["use_case"], 0.0) + record["cost_usd"], 6
            )
            by_model[record["model_id"]] = round(
                by_model.get(record["model_id"], 0.0) + record["cost_usd"], 6
            )
        return {
            "calls": len(self.records),
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost,
            "avg_latency_ms_p50": avg_latency,
            "cost_by_team": by_team,
            "cost_by_use_case": by_use_case,
            "cost_by_model": by_model,
        }

    def recommend_model(self, eval_pass_rates: dict[str, float]) -> str | None:
        """Cheapest model whose eval pass rate is at least 0.8, if any."""
        cheapest: str | None = None
        cheapest_cost: float | None = None
        for model_id, rate in eval_pass_rates.items():
            if rate < 0.8:
                continue
            cost = sum(
                r["cost_usd"] for r in self.records if r["model_id"] == model_id
            )
            if cheapest_cost is None or cost < cheapest_cost:
                cheapest_cost = cost
                cheapest = model_id
        return cheapest
