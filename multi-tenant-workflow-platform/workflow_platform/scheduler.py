"""Run planning: execution order, backfills, retries, tenant quotas."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .dags import Dag


@dataclass
class TenantQuota:
    tenant: str
    max_concurrent_tasks: int
    max_runs_per_day: int


@dataclass
class TaskRun:
    task_id: str
    attempt: int
    state: str  # planned | queued | quota_blocked


@dataclass
class RunPlan:
    dag_id: str
    tenant: str
    logical_date: date
    task_runs: list[TaskRun] = field(default_factory=list)

    def blocked_tasks(self) -> list[str]:
        return [t.task_id for t in self.task_runs if t.state == "quota_blocked"]


def plan_run(dag: Dag, logical_date: date, quota: TenantQuota,
             already_running: int = 0) -> RunPlan:
    """Plan one DAG run in topo order, honouring the tenant's concurrency quota."""
    plan = RunPlan(dag_id=dag.dag_id, tenant=dag.tenant, logical_date=logical_date)
    slots = max(0, quota.max_concurrent_tasks - already_running)
    for i, task_id in enumerate(dag.topo_order()):
        state = "queued" if i < slots else "quota_blocked"
        plan.task_runs.append(TaskRun(task_id=task_id, attempt=1, state=state))
    return plan


def plan_backfill(dag: Dag, start: date, end: date,
                  quota: TenantQuota) -> list[RunPlan]:
    """One run plan per day in [start, end]; stops at the daily run quota."""
    plans: list[RunPlan] = []
    current = start
    while current <= end and len(plans) < quota.max_runs_per_day * ((end - start).days + 1):
        plans.append(plan_run(dag, current, quota))
        current += timedelta(days=1)
    return plans


def retry_schedule(task_retries: int, base_delay_seconds: int = 60,
                   cap_seconds: int = 1800) -> list[int]:
    """Exponential backoff delays (seconds) for each retry attempt."""
    return [min(cap_seconds, base_delay_seconds * (2 ** i)) for i in range(task_retries)]
