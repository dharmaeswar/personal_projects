"""Model routing: match each SDLC task to the cheapest model that can do it.

A code-generation task needs a strong model; a lint-style review pass does
not. Routing on capability first and cost second keeps model spend down
without shipping weaker output where it matters. Latency budgets filter
out models that cannot answer in time. Every routing decision is recorded
in a spend ledger the observability layer reports on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Minimum capability (0-1) each task type needs. Set from the benchmark
# suite in benchmarks.py: tasks below the floor fail measurably more often.
REQUIRED_CAPABILITY = {
    "codegen": 0.80,
    "review": 0.65,
    "testgen": 0.70,
    "triage": 0.50,
    "summarize": 0.40,
}


@dataclass(frozen=True)
class Model:
    name: str
    capability: float  # 0-1, measured on the benchmark suite
    cost_per_1k_tokens: float  # dollars
    latency_ms_per_1k_tokens: float


@dataclass
class RouteDecision:
    model: Model
    task_type: str
    tokens: int
    estimated_cost: float
    estimated_latency_ms: float
    reason: str


@dataclass
class SpendLedger:
    entries: list[RouteDecision] = field(default_factory=list)

    def record(self, decision: RouteDecision) -> None:
        self.entries.append(decision)

    def total_cost(self) -> float:
        return round(sum(d.estimated_cost for d in self.entries), 4)

    def cost_by_model(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for d in self.entries:
            totals[d.model.name] = round(totals.get(d.model.name, 0.0) + d.estimated_cost, 4)
        return totals


class ModelRouter:
    """Cheapest model meeting the capability floor; latency budget filters."""

    def __init__(self, models: list[Model]) -> None:
        if not models:
            raise ValueError("router needs at least one model")
        self.models = sorted(models, key=lambda m: m.cost_per_1k_tokens)
        self.ledger = SpendLedger()

    def route(
        self,
        task_type: str,
        tokens: int,
        max_latency_ms: float | None = None,
    ) -> RouteDecision:
        if task_type not in REQUIRED_CAPABILITY:
            raise ValueError(f"unknown task type: {task_type}")
        if tokens <= 0:
            raise ValueError("tokens must be positive")
        floor = REQUIRED_CAPABILITY[task_type]
        candidates = [m for m in self.models if m.capability >= floor]
        if not candidates:
            raise ValueError(f"no model meets capability floor {floor} for {task_type}")
        if max_latency_ms is not None:
            within_budget = [
                m for m in candidates
                if m.latency_ms_per_1k_tokens * tokens / 1000 <= max_latency_ms
            ]
            if not within_budget:
                raise ValueError(f"no model meets latency budget {max_latency_ms}ms")
            candidates = within_budget
        model = candidates[0]  # cheapest that qualifies
        decision = RouteDecision(
            model=model,
            task_type=task_type,
            tokens=tokens,
            estimated_cost=round(model.cost_per_1k_tokens * tokens / 1000, 4),
            estimated_latency_ms=round(model.latency_ms_per_1k_tokens * tokens / 1000, 2),
            reason=f"cheapest model with capability >= {floor}",
        )
        self.ledger.record(decision)
        return decision
