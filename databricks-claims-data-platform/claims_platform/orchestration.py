"""ADF-style orchestration: a declarative pipeline definition + a DAG runner.

pipelines/claims_daily.json mirrors an Azure Data Factory pipeline: activities
with dependencies, retry policy, and run-state tracking. The runner executes
activities in dependency order, retries a failed activity up to its retry
count, and writes a run log — the same shape ADF / Databricks Workflows
would produce, executed locally so every run is reproducible.
"""
import json
import os
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPELINE_PATH = os.path.join(BASE, "pipelines", "claims_daily.json")


def load_pipeline(path=PIPELINE_PATH):
    with open(path) as f:
        return json.load(f)


def topo_order(activities):
    """Activities in dependency order (Kahn's algorithm); raises on a cycle."""
    deps = {a["name"]: set(a.get("dependsOn", [])) for a in activities}
    order, ready = [], [n for n, d in deps.items() if not d]
    while ready:
        name = ready.pop(0)
        order.append(name)
        for other, d in deps.items():
            if name in d:
                d.discard(name)
                if not d:
                    ready.append(other)
    if len(order) != len(activities):
        raise ValueError("pipeline has a dependency cycle")
    return order


def run_pipeline(pipeline, execute):
    """Execute each activity via execute(name) -> None; returns the run log."""
    order = topo_order(pipeline["activities"])
    log = {"pipeline": pipeline["name"], "activities": {}, "status": "Succeeded"}
    for name in order:
        activity = next(a for a in pipeline["activities"] if a["name"] == name)
        attempts = 0
        while True:
            attempts += 1
            started = time.time()
            try:
                execute(name)
                log["activities"][name] = {
                    "status": "Succeeded", "attempts": attempts,
                    "duration_s": round(time.time() - started, 3)}
                break
            except Exception as exc:  # noqa: BLE001 - retried per policy, then recorded
                if attempts > activity.get("retry", 0):
                    log["activities"][name] = {
                        "status": "Failed", "attempts": attempts,
                        "error": str(exc),
                        "duration_s": round(time.time() - started, 3)}
                    log["status"] = "Failed"
                    return log
    return log
