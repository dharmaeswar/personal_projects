"""Job orchestration and scheduling for the post-trade compute cluster.

A small DAG scheduler in the shape of the job orchestration HRT runs on
its compute cluster: each post-trade stage is a job with dependencies,
jobs run on a worker pool, a failed job is retried, and downstream jobs
are skipped (never run on stale inputs) when a dependency fails. The
scheduler is deterministic about ordering and honest about failure: a
job's status, attempts, duration and error are all recorded in the
returned report.

This is a local, in-process scheduler. It does not claim to be a
distributed system; the worker pool models how independent jobs share
a cluster's workers.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field


@dataclass
class Job:
    """One unit of scheduled work.

    ``func`` receives the shared context dict (results of finished jobs
    live under their job names) and returns the job's result.
    ``max_retries`` is the number of extra attempts after the first.
    """

    name: str
    func: object  # callable[[dict], object]
    deps: list = field(default_factory=list)
    max_retries: int = 1


@dataclass
class JobResult:
    """Outcome of one job in a DAG run."""

    name: str
    status: str  # SUCCEEDED, FAILED, SKIPPED
    attempts: int
    duration_seconds: float
    error: str | None = None
    result: object = None


@dataclass
class DagReport:
    """Outcome of a whole DAG run."""

    results: dict  # name -> JobResult
    succeeded: int
    failed: int
    skipped: int

    @property
    def ok(self) -> bool:
        """True when every job succeeded and none failed or skipped."""
        return self.failed == 0 and self.skipped == 0


def topological_levels(jobs):
    """Group jobs into dependency levels (Kahn's algorithm).

    Raises ValueError on duplicate names, unknown dependencies, or a
    dependency cycle. Each level lists jobs whose dependencies are all
    in earlier levels, so jobs in one level may run in parallel.
    """
    by_name = {}
    for job in jobs:
        if job.name in by_name:
            raise ValueError(f"duplicate job name: {job.name}")
        by_name[job.name] = job
    for job in jobs:
        for dep in job.deps:
            if dep not in by_name:
                raise ValueError(f"job {job.name} depends on unknown job {dep}")
    remaining = {job.name: set(job.deps) for job in jobs}
    levels = []
    while remaining:
        ready = sorted(name for name, deps in remaining.items() if not deps)
        if not ready:
            raise ValueError(
                "dependency cycle among: " + ", ".join(sorted(remaining))
            )
        levels.append([by_name[name] for name in ready])
        for name in ready:
            del remaining[name]
        for deps in remaining.values():
            deps.difference_update(ready)
    return levels


def run_dag(jobs, max_workers=4):
    """Run a list of Jobs respecting dependencies.

    Jobs in the same dependency level run on a worker pool. A job that
    raises is retried up to ``max_retries`` times; if it still fails,
    its dependents are skipped. Returns a DagReport; the shared
    context (job name -> result) is available on each JobResult.
    """
    levels = topological_levels(jobs)
    context = {}
    results = {}
    failed_names = set()
    for level in levels:
        runnable = [j for j in level if not (set(j.deps) & failed_names)]
        for job in level:
            if job not in runnable:
                results[job.name] = JobResult(
                    name=job.name, status="SKIPPED", attempts=0,
                    duration_seconds=0.0,
                    error="skipped: dependency failed",
                )
        if not runnable:
            continue
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_run_job, job, context): job for job in runnable}
            for future in as_completed(futures):
                job = futures[future]
                outcome = future.result()
                results[job.name] = outcome
                if outcome.status == "SUCCEEDED":
                    context[job.name] = outcome.result
                else:
                    failed_names.add(job.name)
    succeeded = sum(1 for r in results.values() if r.status == "SUCCEEDED")
    failed = sum(1 for r in results.values() if r.status == "FAILED")
    skipped = sum(1 for r in results.values() if r.status == "SKIPPED")
    return DagReport(results=results, succeeded=succeeded, failed=failed, skipped=skipped)


def _run_job(job, context):
    """Run one job with retries; never raises."""
    attempts = 0
    started = time.monotonic()
    last_error = None
    while attempts <= job.max_retries:
        attempts += 1
        try:
            result = job.func(context)
            return JobResult(
                name=job.name, status="SUCCEEDED", attempts=attempts,
                duration_seconds=time.monotonic() - started, result=result,
            )
        except Exception as exc:  # noqa: BLE001 - retried, then recorded
            last_error = f"{type(exc).__name__}: {exc}"
    return JobResult(
        name=job.name, status="FAILED", attempts=attempts,
        duration_seconds=time.monotonic() - started, error=last_error,
    )
