"""Small DAG orchestrator for the pipeline.

Tasks declare dependencies; the runner orders them topologically, retries a
task once on a transient failure, and records run state so a re-run with the
same run id skips tasks that already succeeded with the same inputs instead
of redoing them. This mirrors the workflow-orchestration step of the JD's
"configurable pipelines and shared components".
"""

import hashlib
import json


class Task:
    def __init__(self, name, deps, fn, transient=False):
        self.name = name
        self.deps = list(deps)
        self.fn = fn
        self.transient = transient  # may fail once, then succeed on retry


def _topo_order(tasks):
    order, visiting, done = [], set(), set()

    def visit(name):
        if name in done:
            return
        if name in visiting:
            raise ValueError(f"cycle at task {name}")
        visiting.add(name)
        for dep in tasks[name].deps:
            if dep not in tasks:
                raise ValueError(f"task {name} depends on unknown task {dep}")
            visit(dep)
        visiting.discard(name)
        done.add(name)
        order.append(name)

    for name in tasks:
        visit(name)
    return order


class DagRunner:
    def __init__(self, tasks):
        self.tasks = {t.name: t for t in tasks}
        self.run_state = {}  # task name -> {"status": ..., "input_hash": ...}
        self.attempts = {}

    @staticmethod
    def _hash_inputs(inputs):
        return hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()[:12]

    def run(self, run_id, inputs):
        """Run the DAG. Returns {task: result}. Skips tasks already done for
        this run id with identical inputs (resume)."""
        order = _topo_order(self.tasks)
        results = {}
        for name in order:
            task = self.tasks[name]
            input_hash = self._hash_inputs(inputs.get(name, {}))
            state = self.run_state.get(f"{run_id}:{name}")
            if state and state["input_hash"] == input_hash and state["status"] == "done":
                results[name] = state["result"]
                continue
            attempt = 0
            while True:
                attempt += 1
                self.attempts[name] = attempt
                try:
                    result = task.fn()
                    break
                except Exception:
                    if task.transient and attempt == 1:
                        continue
                    raise
            self.run_state[f"{run_id}:{name}"] = {
                "status": "done", "input_hash": input_hash, "result": result,
            }
            results[name] = result
        return results
