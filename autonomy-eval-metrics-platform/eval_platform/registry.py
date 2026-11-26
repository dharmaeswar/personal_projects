"""Versioned metric registry.

A metric definition is immutable once registered: changing a metric creates
a new version, and old evaluation results keep pointing at the version they
were computed with. That is what makes comparisons across model versions
valid — the definition behind a number never silently changes under it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

AGGREGATIONS = ("mean", "rate", "count", "p95", "max")


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    version: int
    description: str
    unit: str
    aggregation: str
    slice_dims: tuple[str, ...] = ()
    higher_is_better: bool = True
    deprecated: bool = False

    def __post_init__(self):
        if self.aggregation not in AGGREGATIONS:
            raise ValueError(f"unknown aggregation {self.aggregation!r}")
        if not self.name or " " in self.name:
            raise ValueError(f"bad metric name {self.name!r}")


class MetricRegistry:
    def __init__(self):
        self._defs: dict[str, list[MetricDefinition]] = {}

    def register(self, name: str, description: str, unit: str, aggregation: str,
                 slice_dims: tuple[str, ...] = (),
                 higher_is_better: bool = True) -> MetricDefinition:
        versions = self._defs.setdefault(name, [])
        version = MetricDefinition(name, len(versions) + 1, description, unit,
                                   aggregation, tuple(slice_dims), higher_is_better)
        versions.append(version)
        return version

    def latest(self, name: str) -> MetricDefinition | None:
        versions = self._defs.get(name)
        return versions[-1] if versions else None

    def get(self, name: str, version: int) -> MetricDefinition | None:
        for v in self._defs.get(name, []):
            if v.version == version:
                return v
        return None

    def deprecate(self, name: str, version: int) -> MetricDefinition:
        old = self.get(name, version)
        if old is None:
            raise ValueError(f"no such metric {name} v{version}")
        new = MetricDefinition(old.name, old.version, old.description, old.unit,
                               old.aggregation, old.slice_dims, old.higher_is_better,
                               deprecated=True)
        self._defs[name][version - 1] = new
        return new

    def names(self) -> list[str]:
        return sorted(self._defs)
