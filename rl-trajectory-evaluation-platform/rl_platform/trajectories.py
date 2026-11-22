"""Trajectory recording and inspection.

A trajectory is one episode of an agent acting inside an environment: an
ordered list of steps (observation, action, reward, done). The recorder
validates step order and reward ranges so broken episodes are flagged
instead of silently entering evaluation data.
"""


def validate_steps(env, steps):
    errors = []
    if not isinstance(steps, list) or not steps:
        return ["trajectory needs at least one step"]
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append("step %d must be an object" % i)
            continue
        if "observation" not in step or "action" not in step:
            errors.append("step %d needs observation and action" % i)
        reward = step.get("reward")
        if not isinstance(reward, (int, float)):
            errors.append("step %d reward must be a number" % i)
        elif not (env["reward"]["min"] <= reward <= env["reward"]["max"]):
            errors.append("step %d reward %s outside [%s, %s]" % (i, reward, env["reward"]["min"], env["reward"]["max"]))
        if step.get("done") and i != len(steps) - 1:
            errors.append("step %d sets done before the final step" % i)
    return errors


def record_trajectory(store, env_id, agent, steps):
    """Record a trajectory; invalid steps are stored with their errors flagged."""
    from .store import next_id

    env = store["environments"].get(env_id)
    if env is None:
        return None, ["environment %s not found" % env_id]
    errors = validate_steps(env, steps)
    traj_id = next_id(store, "traj")
    traj = {
        "id": traj_id,
        "env_id": env_id,
        "agent": agent,
        "steps": steps,
        "valid": not errors,
        "errors": errors,
    }
    store["trajectories"][traj_id] = traj
    return traj, errors


def trajectory_stats(traj):
    rewards = [s.get("reward", 0) for s in traj["steps"] if isinstance(s.get("reward"), (int, float))]
    total = sum(rewards)
    return {
        "id": traj["id"],
        "length": len(traj["steps"]),
        "total_reward": total,
        "mean_reward": (total / len(rewards)) if rewards else 0.0,
        "terminated": bool(traj["steps"] and traj["steps"][-1].get("done")),
        "valid": traj["valid"],
        "error_count": len(traj["errors"]),
    }


def find_broken_trajectories(store, env_id=None):
    """Trajectories that are invalid or never terminated."""
    out = []
    for traj in store["trajectories"].values():
        if env_id is not None and traj["env_id"] != env_id:
            continue
        stats = trajectory_stats(traj)
        if not stats["valid"] or not stats["terminated"]:
            out.append(stats)
    return out


def list_trajectories(store, env_id=None, agent=None, valid_only=False):
    trajs = list(store["trajectories"].values())
    if env_id is not None:
        trajs = [t for t in trajs if t["env_id"] == env_id]
    if agent is not None:
        trajs = [t for t in trajs if t["agent"] == agent]
    if valid_only:
        trajs = [t for t in trajs if t["valid"]]
    return sorted(trajs, key=lambda t: t["id"])
