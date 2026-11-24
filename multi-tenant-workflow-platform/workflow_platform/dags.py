"""DAG model, validation, and the tenant-isolated registry."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Task:
    task_id: str
    image: str
    command: list[str]
    upstream: list[str] = field(default_factory=list)
    retries: int = 2
    cpu: str = "500m"
    memory: str = "512Mi"
    inputs: list[str] = field(default_factory=list)   # catalog dataset ids read
    outputs: list[str] = field(default_factory=list)  # catalog dataset ids written


@dataclass
class Dag:
    dag_id: str
    tenant: str
    schedule: str  # cron-like string, kept opaque on purpose
    tasks: list[Task]

    def task_map(self) -> dict[str, Task]:
        return {t.task_id: t for t in self.tasks}

    def validate(self) -> list[str]:
        """Return a list of problems; empty means the DAG is valid."""
        problems: list[str] = []
        ids = [t.task_id for t in self.tasks]
        if len(ids) != len(set(ids)):
            problems.append(f"dag {self.dag_id}: duplicate task ids")
        known = set(ids)
        for t in self.tasks:
            for up in t.upstream:
                if up not in known:
                    problems.append(
                        f"dag {self.dag_id}: task {t.task_id} depends on unknown task {up}"
                    )
            if t.retries < 0:
                problems.append(f"dag {self.dag_id}: task {t.task_id} has negative retries")
        if self._has_cycle():
            problems.append(f"dag {self.dag_id}: dependency cycle detected")
        return problems

    def _has_cycle(self) -> bool:
        graph = {t.task_id: list(t.upstream) for t in self.tasks}
        visiting, done = set(), set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in done:
                return False
            visiting.add(node)
            for up in graph.get(node, []):
                if up in graph and visit(up):
                    return True
            visiting.discard(node)
            done.add(node)
            return False

        return any(visit(n) for n in graph)

    def topo_order(self) -> list[str]:
        """Task ids in a valid execution order (upstream first)."""
        order, seen = [], set()
        graph = self.task_map()

        def visit(node: str) -> None:
            if node in seen:
                return
            for up in graph[node].upstream:
                if up in graph:
                    visit(up)
            seen.add(node)
            order.append(node)

        for t in self.tasks:
            visit(t.task_id)
        return order


class TenantRegistry:
    """Registry that keeps each tenant's DAGs isolated from the others."""

    def __init__(self) -> None:
        self._dags: dict[str, dict[str, Dag]] = {}

    def register(self, dag: Dag) -> list[str]:
        problems = dag.validate()
        if problems:
            return problems
        self._dags.setdefault(dag.tenant, {})[dag.dag_id] = dag
        return []

    def get(self, tenant: str, dag_id: str) -> Dag | None:
        return self._dags.get(tenant, {}).get(dag_id)

    def list_for_tenant(self, tenant: str) -> list[str]:
        return sorted(self._dags.get(tenant, {}))

    def tenants(self) -> list[str]:
        return sorted(self._dags)
