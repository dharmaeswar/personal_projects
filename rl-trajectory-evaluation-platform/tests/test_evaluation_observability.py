from rl_platform import environments, evaluation, observability, quality
from rl_platform.store import new_store


def _seed(store):
    spec = {
        "name": "math-reasoning-env",
        "task_type": "math-reasoning",
        "observation_fields": ["problem"],
        "action_fields": ["answer"],
        "reward": {"type": "sparse", "min": 0, "max": 1},
    }
    env, _ = environments.register_environment(store, spec)
    from rl_platform import trajectories
    good = [
        {"observation": "2+2", "action": "4", "reward": 1, "done": True},
    ]
    bad_reward = [
        {"observation": "3+3", "action": "5", "reward": 0, "done": True},
    ]
    no_end = [
        {"observation": "4+4", "action": "8", "reward": 1, "done": False},
    ]
    trajectories.record_trajectory(store, env["id"], "model-a", good)
    trajectories.record_trajectory(store, env["id"], "model-a", bad_reward)
    trajectories.record_trajectory(store, env["id"], "model-a", no_end)
    return env


def test_evaluation_pass_rate_and_failure_modes():
    store = new_store()
    env = _seed(store)
    run, errors = evaluation.run_evaluation(store, env["id"], "model-a", reward_threshold=1)
    assert errors == []
    assert run["trajectories_scored"] == 3
    assert run["passed"] == 1
    assert run["pass_rate"] == 0.333
    assert run["failure_modes"] == {"low_reward": 1, "no_termination": 1}


def test_evaluation_no_trajectories_errors():
    store = new_store()
    env, _ = environments.register_environment(store, {
        "name": "e", "task_type": "dialogue", "observation_fields": ["text"],
        "action_fields": ["reply"], "reward": {"type": "sparse", "min": 0, "max": 1}})
    run, errors = evaluation.run_evaluation(store, env["id"], "model-a")
    assert run is None and errors


def test_evaluation_unknown_environment():
    store = new_store()
    run, errors = evaluation.run_evaluation(store, "env-9999", "model-a")
    assert run is None and errors


def test_summarize_model_behavior():
    store = new_store()
    env = _seed(store)
    evaluation.run_evaluation(store, env["id"], "model-a", reward_threshold=1)
    summary = evaluation.summarize_model_behavior(store, "model-a")
    assert summary["by_task_type"]["math-reasoning"]["pass_rate"] == 0.333
    assert summary["top_failure_modes"][0][1] == 1


def test_collection_progress():
    store = new_store()
    env = _seed(store)
    progress = observability.collection_progress(store, {env["id"]: 10})
    assert progress[env["id"]]["collected"] == 3
    assert progress[env["id"]]["progress"] == 0.3
    assert progress[env["id"]]["remaining"] == 7


def test_pipeline_health_flags_stale_feed():
    store = new_store()
    observability.record_pipeline_event(store, "trajectory-ingest", "ok", 30)
    observability.record_pipeline_event(store, "eval-results", "ok", 7200, error_count=2)
    health = observability.pipeline_health(store)
    assert health["trajectory-ingest"]["healthy"] is True
    assert health["eval-results"]["stale"] is True
    assert health["eval-results"]["healthy"] is False
    assert health["eval-results"]["error_rate"] == 2.0


def test_environment_quality_blends_reviews_and_validity():
    store = new_store()
    env = _seed(store)
    task, _ = quality.create_task(store, env["id"], "What is 2+2?")
    quality.review_task(store, task["id"], "rev-1", {
        "instruction_clarity": 5, "solvability": 5, "reward_correctness": 5,
        "no_leakage": 5, "coverage": 5})
    q = observability.environment_quality(store)[env["id"]]
    assert q["review_mean"] == 5.0
    assert q["trajectory_validity"] == 1.0
    assert q["quality_score"] == 1.0


def test_dashboard_counts():
    store = new_store()
    env = _seed(store)
    dash = observability.dashboard(store, {env["id"]: 10})
    assert dash["counts"] == {"environments": 1, "trajectories": 3, "tasks": 0, "eval_runs": 0}
    assert env["id"] in dash["environment_quality"]
    assert env["id"] in dash["collection_progress"]
