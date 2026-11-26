"""Agent runtime: concurrent execution, retry with backoff, step budgets.

An agent is a list of steps. Each step is a callable that receives a
context dict and returns a value (or raises). The runtime executes steps
in order, enforces a per-run step budget, retries a failing step with
exponential backoff, records every attempt, and can run many agents
concurrently in a thread pool. Step results are kept in a run trace so
a caller can audit exactly what happened, in order.
"""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

StepFn = Callable[[Dict[str, Any]], Any]


@dataclass
class AgentStep:
    """One unit of agent work."""

    name: str
    fn: StepFn
    max_retries: int = 2
    backoff_seconds: float = 0.05


@dataclass
class StepResult:
    name: str
    status: str  # "ok" | "failed" | "skipped"
    value: Any = None
    error: Optional[str] = None
    attempts: int = 0
    elapsed_seconds: float = 0.0


@dataclass
class RunResult:
    agent_name: str
    status: str  # "completed" | "failed" | "budget_exceeded"
    steps: List[StepResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status == "completed"

    def values(self) -> Dict[str, Any]:
        return {s.name: s.value for s in self.steps if s.status == "ok"}


@dataclass
class AgentTask:
    name: str
    steps: List[AgentStep]
    max_steps: int = 50
    context: Dict[str, Any] = field(default_factory=dict)


class BudgetExceeded(Exception):
    """Raised when a run would execute more steps than its budget allows."""


class AgentRuntime:
    """Runs agent tasks with budgets, retries, and concurrency."""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers

    def run(self, task: AgentTask) -> RunResult:
        started = time.monotonic()
        results: List[StepResult] = []
        if len(task.steps) > task.max_steps:
            for step in task.steps[: task.max_steps]:
                results.append(
                    StepResult(name=step.name, status="skipped",
                               error="step budget exceeded")
                )
            return RunResult(
                agent_name=task.name,
                status="budget_exceeded",
                steps=results,
                elapsed_seconds=time.monotonic() - started,
            )
        for step in task.steps:
            results.append(self._run_step(step, task.context))
            if results[-1].status == "failed":
                return RunResult(
                    agent_name=task.name,
                    status="failed",
                    steps=results,
                    elapsed_seconds=time.monotonic() - started,
                )
        return RunResult(
            agent_name=task.name,
            status="completed",
            steps=results,
            elapsed_seconds=time.monotonic() - started,
        )

    def _run_step(self, step: AgentStep, context: Dict[str, Any]) -> StepResult:
        started = time.monotonic()
        attempts = 0
        last_error: Optional[str] = None
        while attempts <= step.max_retries:
            attempts += 1
            try:
                value = step.fn(context)
                context[step.name] = value
                return StepResult(
                    name=step.name,
                    status="ok",
                    value=value,
                    attempts=attempts,
                    elapsed_seconds=time.monotonic() - started,
                )
            except Exception as exc:  # noqa: BLE001 - retry any step failure
                last_error = f"{type(exc).__name__}: {exc}"
                if attempts <= step.max_retries:
                    time.sleep(step.backoff_seconds * (2 ** (attempts - 1)))
        return StepResult(
            name=step.name,
            status="failed",
            error=last_error,
            attempts=attempts,
            elapsed_seconds=time.monotonic() - started,
        )

    def run_many(self, tasks: List[AgentTask]) -> List[RunResult]:
        """Run several agents concurrently; results come back in task order."""
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as pool:
            return list(pool.map(self.run, tasks))
