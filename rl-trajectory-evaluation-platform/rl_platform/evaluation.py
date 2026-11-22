"""Evaluation runs: score model behaviour over trajectories.

An evaluation run takes the valid trajectories for one environment, checks
each against a reward threshold and a termination requirement, and reports
a pass rate plus the failure modes behind the failures — the numbers a
research team reads before trusting a model on that environment.
"""

FAILURE_NO_TERMINATION = "no_termination"
FAILURE_LOW_REWARD = "low_reward"
FAILURE_INVALID = "invalid_trajectory"


def run_evaluation(store, env_id, model_name, reward_threshold=0.0):
    """Score every trajectory of an environment for one model."""
    from .store import next_id
    from .trajectories import trajectory_stats

    env = store["environments"].get(env_id)
    if env is None:
        return None, ["environment %s not found" % env_id]
    trajs = [t for t in store["trajectories"].values() if t["env_id"] == env_id]
    if not trajs:
        return None, ["no trajectories recorded for environment %s" % env_id]
    results, failures = [], {}
    for traj in trajs:
        stats = trajectory_stats(traj)
        if not stats["valid"]:
            outcome, mode = "fail", FAILURE_INVALID
        elif not stats["terminated"]:
            outcome, mode = "fail", FAILURE_NO_TERMINATION
        elif stats["total_reward"] < reward_threshold:
            outcome, mode = "fail", FAILURE_LOW_REWARD
        else:
            outcome, mode = "pass", None
        if mode:
            failures[mode] = failures.get(mode, 0) + 1
        results.append({"trajectory_id": traj["id"], "outcome": outcome, "total_reward": stats["total_reward"]})
    passed = sum(1 for r in results if r["outcome"] == "pass")
    run_id = next_id(store, "run")
    run = {
        "id": run_id,
        "env_id": env_id,
        "model_name": model_name,
        "reward_threshold": reward_threshold,
        "trajectories_scored": len(results),
        "passed": passed,
        "pass_rate": round(passed / len(results), 3),
        "failure_modes": failures,
        "results": results,
    }
    store["eval_runs"][run_id] = run
    return run, []


def summarize_model_behavior(store, model_name=None):
    """Pass rates by task type and the most common failure modes."""
    runs = [r for r in store["eval_runs"].values() if model_name is None or r["model_name"] == model_name]
    by_task, failures = {}, {}
    for run in runs:
        env = store["environments"].get(run["env_id"])
        task_type = env["task_type"] if env else "unknown"
        agg = by_task.setdefault(task_type, {"runs": 0, "scored": 0, "passed": 0})
        agg["runs"] += 1
        agg["scored"] += run["trajectories_scored"]
        agg["passed"] += run["passed"]
        for mode, count in run["failure_modes"].items():
            failures[mode] = failures.get(mode, 0) + count
    summary = {}
    for task_type, agg in by_task.items():
        summary[task_type] = {
            "runs": agg["runs"],
            "pass_rate": round(agg["passed"] / agg["scored"], 3) if agg["scored"] else None,
        }
    top_failures = sorted(failures.items(), key=lambda kv: kv[1], reverse=True)
    return {"by_task_type": summary, "top_failure_modes": top_failures}
