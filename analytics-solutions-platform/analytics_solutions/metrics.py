"""Governed metrics — one source of truth for metric definitions.

A metric exists only in the registry: name, plain-language definition,
formula, owner, grain and source tables. Computing a metric requires a
registered definition; redefining the same name with a different formula
is rejected, so two dashboards can never disagree about what a number
means.
"""

from __future__ import annotations


class MetricRegistryError(ValueError):
    pass


class MetricRegistry:
    """The single registry of governed metric definitions."""

    def __init__(self):
        self._metrics: dict[str, dict] = {}

    def register(self, name: str, definition: str, formula: str, owner: str,
                 grain: str, source_tables: list[str]) -> dict:
        if not name or not definition or not formula:
            raise MetricRegistryError("metric needs a name, definition and formula")
        entry = {
            "name": name,
            "definition": definition,
            "formula": formula,
            "owner": owner,
            "grain": grain,
            "source_tables": list(source_tables),
        }
        existing = self._metrics.get(name)
        if existing is not None and existing != entry:
            raise MetricRegistryError(
                f"conflicting redefinition of metric '{name}': "
                f"existing formula '{existing['formula']}' vs new '{formula}'")
        self._metrics[name] = entry
        return entry

    def get(self, name: str) -> dict:
        if name not in self._metrics:
            raise MetricRegistryError(f"metric '{name}' is not registered")
        return self._metrics[name]

    def names(self) -> list[str]:
        return sorted(self._metrics)


def compute_metrics(registry: MetricRegistry, facts: list[dict]) -> dict[str, float | int]:
    """Compute every registered metric over the fact rows.

    Supported formulas (named in the registry, computed here):
    - ``count_active_policies`` — rows with is_active true
    - ``total_premium_active`` — sum of premium_annual over active rows
    - ``avg_premium_active`` — mean premium_annual over active rows
    - ``active_policy_share`` — active rows / all rows
    - ``avg_activity_30d`` — mean activity_count_30d over active rows
    Unknown formulas raise, so a metric is never silently miscomputed.
    """
    active = [f for f in facts if f["is_active"]]
    results: dict[str, float | int] = {}
    for name in registry.names():
        formula = registry.get(name)["formula"]
        if formula == "count_active_policies":
            results[name] = len(active)
        elif formula == "total_premium_active":
            results[name] = round(sum(f["premium_annual"] for f in active), 2)
        elif formula == "avg_premium_active":
            results[name] = round(sum(f["premium_annual"] for f in active) / len(active), 2) if active else 0.0
        elif formula == "active_policy_share":
            results[name] = round(len(active) / len(facts), 4) if facts else 0.0
        elif formula == "avg_activity_30d":
            results[name] = round(sum(f["activity_count_30d"] for f in active) / len(active), 2) if active else 0.0
        else:
            raise MetricRegistryError(f"no computation for formula '{formula}'")
    return results
