"""Tiny JSON API layer over the service modules (standard library only).

`handle` routes a method + path to the platform services and returns a
(status_code, payload) pair, the way the backend service behind the product
surfaces would. It is deliberately framework-free so the whole platform
runs and tests with no installed dependencies.
"""

import json

from . import environments, evaluation, observability, partner, quality, trajectories
from .store import new_store


def _segments(path):
    return [s for s in path.strip("/").split("/") if s]


def handle(store, method, path, body=None):
    body = body or {}
    parts = _segments(path)

    if method == "GET" and parts == ["environments"]:
        return 200, environments.list_environments(
            store, task_type=body.get("task_type"), status=body.get("status")
        )
    if method == "POST" and parts == ["environments"]:
        env, errors = environments.register_environment(store, body)
        if errors:
            return 400, {"errors": errors}
        return 201, env
    if method == "GET" and len(parts) == 3 and parts[0] == "environments" and parts[2] == "trajectories":
        env_id = parts[1]
        if env_id not in store["environments"]:
            return 404, {"errors": ["environment %s not found" % env_id]}
        return 200, trajectories.list_trajectories(store, env_id=env_id)
    if method == "POST" and parts == ["trajectories"]:
        traj, errors = trajectories.record_trajectory(
            store, body.get("env_id"), body.get("agent", "unknown"), body.get("steps", [])
        )
        if traj is None:
            return 404, {"errors": errors}
        if errors:
            return 422, {"trajectory": traj, "errors": errors}
        return 201, traj
    if method == "POST" and parts == ["evaluations"]:
        run, errors = evaluation.run_evaluation(
            store, body.get("env_id"), body.get("model_name", "unknown"),
            body.get("reward_threshold", 0.0),
        )
        if run is None:
            return 400, {"errors": errors}
        return 201, run
    if method == "GET" and parts == ["dashboard"]:
        return 200, observability.dashboard(store, body.get("targets", {}))
    if method == "POST" and parts == ["submissions"]:
        sub = partner.submit_environment(
            store, body.get("partner", "unknown"), body.get("spec", {}), body.get("training_rows", [])
        )
        return 201, sub
    if method == "POST" and len(parts) == 3 and parts[0] == "submissions" and parts[2] == "test":
        sub, errors = partner.test_submission(store, parts[1])
        if sub is None:
            return 404, {"errors": errors}
        return 200, sub
    if method == "POST" and parts == ["reviews"]:
        review, errors = quality.review_task(
            store, body.get("task_id"), body.get("reviewer", "unknown"),
            body.get("scores", {}), body.get("notes", ""),
        )
        if review is None:
            return 400, {"errors": errors}
        return 201, review
    return 404, {"errors": ["no route for %s %s" % (method, path)]}


def demo_store():
    """Seed a small synthetic store: two environments, trajectories, reviews."""
    store = new_store()
    spec = {
        "name": "web-checkout-navigation",
        "task_type": "web-navigation",
        "observation_fields": ["url", "dom_snapshot", "cart_total"],
        "action_fields": ["click", "type", "scroll"],
        "reward": {"type": "sparse", "min": 0, "max": 1},
        "owner": "partner-alpha",
    }
    env, _ = environments.register_environment(store, spec)
    environments.set_environment_status(store, env["id"], "approved")
    steps = [
        {"observation": "cart page", "action": "click checkout", "reward": 0, "done": False},
        {"observation": "checkout form", "action": "type address", "reward": 0, "done": False},
        {"observation": "confirmation", "action": "click confirm", "reward": 1, "done": True},
    ]
    trajectories.record_trajectory(store, env["id"], "agent-7b", steps)
    task, _ = quality.create_task(store, env["id"], "Complete checkout for a cart with two items.")
    quality.review_task(store, task["id"], "reviewer-1", {
        "instruction_clarity": 5, "solvability": 5, "reward_correctness": 4,
        "no_leakage": 5, "coverage": 4,
    })
    observability.record_pipeline_event(store, "trajectory-ingest", "ok", 42)
    return store


if __name__ == "__main__":
    store = demo_store()
    print(json.dumps(observability.dashboard(store, {list(store["environments"])[0]: 10}), indent=2))
