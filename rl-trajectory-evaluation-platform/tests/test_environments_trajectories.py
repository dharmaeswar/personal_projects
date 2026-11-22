import pytest

from rl_platform import environments, trajectories
from rl_platform.store import new_store


def good_spec(**over):
    spec = {
        "name": "web-checkout-navigation",
        "task_type": "web-navigation",
        "observation_fields": ["url", "dom_snapshot"],
        "action_fields": ["click", "type"],
        "reward": {"type": "sparse", "min": 0, "max": 1},
    }
    spec.update(over)
    return spec


def test_register_valid_environment():
    store = new_store()
    env, errors = environments.register_environment(store, good_spec())
    assert errors == []
    assert env["status"] == "draft"
    assert env["id"] in store["environments"]


def test_register_rejects_bad_task_type():
    store = new_store()
    _, errors = environments.register_environment(store, good_spec(task_type="flying"))
    assert any("task_type" in e for e in errors)


def test_register_rejects_bad_reward_range():
    store = new_store()
    _, errors = environments.register_environment(
        store, good_spec(reward={"type": "dense", "min": 5, "max": 1})
    )
    assert any("reward.min" in e for e in errors)


def test_register_rejects_empty_action_fields():
    store = new_store()
    _, errors = environments.register_environment(store, good_spec(action_fields=[]))
    assert errors


def test_list_filters_by_task_type_and_status():
    store = new_store()
    env1, _ = environments.register_environment(store, good_spec())
    env2, _ = environments.register_environment(store, good_spec(name="math-tutor", task_type="math-reasoning"))
    environments.set_environment_status(store, env1["id"], "approved")
    assert [e["id"] for e in environments.list_environments(store, task_type="math-reasoning")] == [env2["id"]]
    assert [e["id"] for e in environments.list_environments(store, status="approved")] == [env1["id"]]


def test_deprecate_environment():
    store = new_store()
    env, _ = environments.register_environment(store, good_spec())
    updated, errors = environments.deprecate_environment(store, env["id"])
    assert errors == [] and updated["status"] == "deprecated"


def test_set_status_unknown_env():
    store = new_store()
    result, errors = environments.set_environment_status(store, "env-9999", "approved")
    assert result is None and errors


def steps_ok():
    return [
        {"observation": "cart", "action": "click checkout", "reward": 0, "done": False},
        {"observation": "done", "action": "click confirm", "reward": 1, "done": True},
    ]


def test_record_valid_trajectory():
    store = new_store()
    env, _ = environments.register_environment(store, good_spec())
    traj, errors = trajectories.record_trajectory(store, env["id"], "agent-7b", steps_ok())
    assert errors == [] and traj["valid"] is True


def test_record_rejects_reward_out_of_range():
    store = new_store()
    env, _ = environments.register_environment(store, good_spec())
    steps = [{"observation": "x", "action": "click", "reward": 9, "done": True}]
    traj, errors = trajectories.record_trajectory(store, env["id"], "agent-7b", steps)
    assert traj["valid"] is False
    assert any("outside" in e for e in errors)


def test_record_flags_done_before_last_step():
    store = new_store()
    env, _ = environments.register_environment(store, good_spec())
    steps = [
        {"observation": "x", "action": "click", "reward": 0, "done": True},
        {"observation": "y", "action": "click", "reward": 1, "done": True},
    ]
    _, errors = trajectories.record_trajectory(store, env["id"], "agent-7b", steps)
    assert any("before the final step" in e for e in errors)


def test_record_unknown_environment():
    store = new_store()
    traj, errors = trajectories.record_trajectory(store, "env-9999", "agent-7b", steps_ok())
    assert traj is None and errors


def test_trajectory_stats():
    store = new_store()
    env, _ = environments.register_environment(store, good_spec())
    traj, _ = trajectories.record_trajectory(store, env["id"], "agent-7b", steps_ok())
    stats = trajectories.trajectory_stats(traj)
    assert stats == {"id": traj["id"], "length": 2, "total_reward": 1,
                     "mean_reward": 0.5, "terminated": True, "valid": True, "error_count": 0}


def test_find_broken_trajectories():
    store = new_store()
    env, _ = environments.register_environment(store, good_spec())
    trajectories.record_trajectory(store, env["id"], "agent-7b", steps_ok())
    broken_steps = [{"observation": "x", "action": "click", "reward": 0, "done": False}]
    bad, _ = trajectories.record_trajectory(store, env["id"], "agent-7b", broken_steps)
    broken = trajectories.find_broken_trajectories(store, env["id"])
    assert [b["id"] for b in broken] == [bad["id"]]
