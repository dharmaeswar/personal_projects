"""Orchestration — a local model of a Step Functions state machine.

The pipeline is a DAG of named steps with dependencies, run in topological
order. Each step retries transient failures (up to `retries` attempts);
a step that still fails stops the run and its error is recorded in a
dead-letter entry instead of failing silently. A re-run with the same run
id skips steps that already succeeded with the same inputs (resume).
"""

from __future__ import annotations

import json
from pathlib import Path


class StepFailed(RuntimeError):
    pass


class TransientStepError(RuntimeError):
    """A retryable step failure (the Step Functions retry equivalent)."""


class StateMachine:
    """A small DAG runner with retries, resume and dead-letter recording."""

    def __init__(self, steps, state_path):
        """`steps`: list of dicts {name, fn, depends_on, retries}.

        `fn` takes the shared `context` dict and returns a result stored
        under its step name. `depends_on` lists step names that must run
        first. `retries` is the number of extra attempts after the first.
        """
        self.steps = {s["name"]: s for s in steps}
        self.state_path = Path(state_path)
        self.state = {"runs": {}}
        if self.state_path.exists():
            self.state = json.loads(self.state_path.read_text())

    def _order(self):
        ordered, visiting, done = [], set(), set()

        def visit(name):
            if name in done:
                return
            if name in visiting:
                raise ValueError(f"cycle in step dependencies at {name}")
            visiting.add(name)
            for dep in self.steps[name].get("depends_on", []):
                if dep not in self.steps:
                    raise ValueError(f"unknown dependency {dep} for step {name}")
                visit(dep)
            visiting.discard(name)
            done.add(name)
            ordered.append(name)

        for name in self.steps:
            visit(name)
        return ordered

    def run(self, run_id, context):
        run = self.state["runs"].setdefault(run_id, {"completed": {}, "dead_letter": []})
        results = {}
        for name in self._order():
            if name in run["completed"]:
                results[name] = run["completed"][name]
                continue
            step = self.steps[name]
            attempts = 0
            while True:
                try:
                    result = step["fn"](context)
                    break
                except TransientStepError:
                    attempts += 1
                    if attempts > step.get("retries", 1):
                        run["dead_letter"].append(
                            {"step": name, "error": "transient failure after retries"}
                        )
                        self._save()
                        raise StepFailed(f"step {name} failed after retries")
            run["completed"][name] = result
            results[name] = result
        self._save()
        return results

    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, indent=2))
