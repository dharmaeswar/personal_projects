"""Invariant framework: registry, outcomes and the scenario runner.

An *invariant* is a function that takes a scenario context (a dict of model
inputs for one asset class under one scenario) and returns an
``Outcome(passed, measured, limit, detail)``. Invariants are registered with
the ``@invariant(asset_class, name)`` decorator, so adding a check for a new
model means writing one function and decorating it -- the runner, reporting
and CLI pick it up automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Outcome:
    """Result of one invariant evaluated on one scenario."""

    passed: bool
    measured: float          # the quantity being checked (e.g. max |breach|)
    limit: float             # the tolerance / bound it is compared against
    detail: str = ""


@dataclass
class Invariant:
    asset_class: str
    name: str
    func: Callable[[dict], Outcome]
    description: str = ""


class InvariantRegistry:
    def __init__(self) -> None:
        self._items: list[Invariant] = []

    def register(self, asset_class: str, name: str, description: str = ""):
        def decorator(func: Callable[[dict], Outcome]) -> Callable[[dict], Outcome]:
            self._items.append(Invariant(asset_class, name, func, description))
            return func
        return decorator

    def for_asset(self, asset_class: str) -> list[Invariant]:
        return [inv for inv in self._items if inv.asset_class == asset_class]

    def asset_classes(self) -> list[str]:
        seen: list[str] = []
        for inv in self._items:
            if inv.asset_class not in seen:
                seen.append(inv.asset_class)
        return seen

    def __len__(self) -> int:
        return len(self._items)


REGISTRY = InvariantRegistry()


def invariant(asset_class: str, name: str, description: str = ""):
    """Decorator: register a function as an invariant for ``asset_class``."""
    return REGISTRY.register(asset_class, name, description)


@dataclass
class CheckResult:
    """One invariant x one scenario, flattened for reporting."""

    scenario_id: str
    asset_class: str
    invariant: str
    passed: bool
    measured: float
    limit: float
    detail: str = ""

    @property
    def status(self) -> str:
        return "PASS" if self.passed else "FAIL"


def run_suite(scenarios: list[dict], registry: InvariantRegistry = REGISTRY) -> list[CheckResult]:
    """Run every registered invariant over every scenario of its asset class.

    ``scenarios`` is a list of dicts with keys ``id``, ``asset_class`` and
    ``context`` (the model inputs handed to each invariant function).
    Exceptions inside an invariant are recorded as failures, never raised, so
    one broken model cannot hide the results of the remaining checks.
    """
    results: list[CheckResult] = []
    for scenario in scenarios:
        for inv in registry.for_asset(scenario["asset_class"]):
            try:
                outcome = inv.func(scenario["context"])
                results.append(CheckResult(
                    scenario_id=scenario["id"],
                    asset_class=inv.asset_class,
                    invariant=inv.name,
                    passed=bool(outcome.passed),
                    measured=float(outcome.measured),
                    limit=float(outcome.limit),
                    detail=outcome.detail,
                ))
            except Exception as exc:  # noqa: BLE001 - a crashing check is a failing check
                results.append(CheckResult(
                    scenario_id=scenario["id"],
                    asset_class=inv.asset_class,
                    invariant=inv.name,
                    passed=False,
                    measured=float("nan"),
                    limit=0.0,
                    detail=f"invariant raised {type(exc).__name__}: {exc}",
                ))
    return results
