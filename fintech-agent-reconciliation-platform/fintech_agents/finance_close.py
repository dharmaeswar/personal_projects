"""Month-end close, consolidation, ARR and billings — the Finance
processes the Veeam Finance Transformation Office automates.

Everything here is deterministic arithmetic on synthetic data:
a close checklist with dependencies, multi-entity consolidation with
FX conversion, an ARR roll-forward, billings vs revenue (deferred
revenue), and forecast variance. No real ERP data, no model calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# -- close checklist ---------------------------------------------------

@dataclass
class CloseTask:
    task_id: str
    name: str
    owner: str  # controllership | fp&a | revenue | tax | treasury
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"  # pending | done


class CloseChecklist:
    """Ordered close tasks; a task can only complete once its
    dependencies are done, so the close cannot skip ahead."""

    def __init__(self, tasks: list[CloseTask]) -> None:
        self.tasks = {t.task_id: t for t in tasks}
        unknown = {d for t in tasks for d in t.depends_on
                   if d not in self.tasks}
        if unknown:
            raise ValueError(f"unknown dependency: {sorted(unknown)}")

    def ordered(self) -> list[CloseTask]:
        done: set[str] = set()
        order: list[CloseTask] = []
        remaining = dict(self.tasks)
        while remaining:
            ready = [t for t in remaining.values()
                     if all(d in done for d in t.depends_on)]
            if not ready:
                raise ValueError("close checklist has a dependency cycle")
            for task in sorted(ready, key=lambda t: t.task_id):
                order.append(task)
                done.add(task.task_id)
                del remaining[task.task_id]
        return order

    def complete(self, task_id: str) -> CloseTask:
        task = self.tasks[task_id]
        blocked = [d for d in task.depends_on
                   if self.tasks[d].status != "done"]
        if blocked:
            raise ValueError(
                f"cannot complete {task_id}: blocked by {blocked}")
        task.status = "done"
        return task

    @property
    def progress(self) -> float:
        if not self.tasks:
            return 1.0
        done = sum(1 for t in self.tasks.values() if t.status == "done")
        return done / len(self.tasks)


# -- consolidation, ARR, billings --------------------------------------

@dataclass(frozen=True)
class EntityResult:
    entity: str
    currency: str
    revenue_minor: int
    fx_to_usd: float
    revenue_usd_minor: int


def consolidate(entities: list[dict]) -> dict:
    """Roll subsidiary results into USD. Each entity gives its local
    revenue (minor units) and its FX rate to USD; the consolidated
    total is the sum of the converted lines, each line kept for audit."""
    lines = []
    for ent in entities:
        converted = int(round(ent["revenue_minor"] * ent["fx_to_usd"]))
        lines.append(EntityResult(ent["entity"], ent["currency"],
                                  ent["revenue_minor"], ent["fx_to_usd"],
                                  converted))
    return {"lines": lines,
            "total_usd_minor": sum(line.revenue_usd_minor
                                   for line in lines)}


def arr_roll_forward(start_minor: int, *, new_minor: int,
                     expansion_minor: int, churn_minor: int,
                     contraction_minor: int) -> dict:
    """ARR bridge: ending ARR and net revenue retention. Churn and
    contraction are passed as positive amounts and subtracted."""
    ending = (start_minor + new_minor + expansion_minor
              - churn_minor - contraction_minor)
    nrr = ((start_minor + expansion_minor - churn_minor
            - contraction_minor) / start_minor * 100) if start_minor else 0.0
    return {"start_minor": start_minor, "new_minor": new_minor,
            "expansion_minor": expansion_minor,
            "churn_minor": churn_minor,
            "contraction_minor": contraction_minor,
            "ending_minor": ending,
            "net_revenue_retention_pct": round(nrr, 2)}


def billings_vs_revenue(billings_minor: int,
                        revenue_minor: int) -> dict:
    """Billings minus recognised revenue is the change in deferred
    revenue for the period (positive = deferred balance grew)."""
    change = billings_minor - revenue_minor
    return {"billings_minor": billings_minor,
            "revenue_minor": revenue_minor,
            "deferred_revenue_change_minor": change}


def forecast_variance(actual_minor: int, forecast_minor: int,
                      *, flag_pct: float = 5.0) -> dict:
    """Forecast vs actual with a flag threshold, the FP&A variance
    view: absolute and percentage variance, flagged when the absolute
    percentage beats the threshold."""
    diff = actual_minor - forecast_minor
    pct = (diff / forecast_minor * 100) if forecast_minor else 0.0
    return {"actual_minor": actual_minor,
            "forecast_minor": forecast_minor,
            "variance_minor": diff, "variance_pct": round(pct, 2),
            "flagged": abs(pct) > flag_pct}
