"""Metadata catalog: dataset registration, connectors, and lineage."""
from __future__ import annotations

from dataclasses import dataclass, field

from .dags import Dag


@dataclass
class Dataset:
    dataset_id: str          # e.g. "snowflake.analytics.daily_sessions"
    store: str               # postgres | snowflake | s3 | kafka
    owner_tenant: str
    columns: list[str] = field(default_factory=list)
    description: str = ""


class Catalog:
    def __init__(self) -> None:
        self._datasets: dict[str, Dataset] = {}
        self._edges: list[tuple[str, str, str]] = []  # (upstream, downstream, via task)

    def register(self, dataset: Dataset) -> None:
        self._datasets[dataset.dataset_id] = dataset

    def get(self, dataset_id: str) -> Dataset | None:
        return self._datasets.get(dataset_id)

    def search(self, text: str) -> list[str]:
        text = text.lower()
        return sorted(
            ds_id for ds_id, ds in self._datasets.items()
            if text in ds_id.lower() or text in ds.description.lower()
        )

    def ingest_dag_lineage(self, dag: Dag) -> None:
        """Record dataset -> dataset lineage implied by a DAG's tasks."""
        for task in dag.tasks:
            for src in task.inputs:
                for dst in task.outputs:
                    self._edges.append((src, dst, f"{dag.dag_id}.{task.task_id}"))

    def upstream_of(self, dataset_id: str) -> list[str]:
        return sorted({src for src, dst, _ in self._edges if dst == dataset_id})

    def downstream_of(self, dataset_id: str) -> list[str]:
        return sorted({dst for src, dst, _ in self._edges if src == dataset_id})

    def impact_of(self, dataset_id: str) -> list[str]:
        """Every dataset reachable downstream (what breaks if this one changes)."""
        seen, stack = set(), [dataset_id]
        while stack:
            node = stack.pop()
            for nxt in self.downstream_of(node):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return sorted(seen)


@dataclass
class Connector:
    """A catalog connector for one store type; ingests dataset metadata."""
    store: str

    def ingest(self, catalog: Catalog, tenant: str,
               tables: dict[str, list[str]]) -> int:
        count = 0
        for table, columns in tables.items():
            catalog.register(Dataset(
                dataset_id=f"{self.store}.{tenant}.{table}",
                store=self.store,
                owner_tenant=tenant,
                columns=columns,
            ))
            count += 1
        return count
