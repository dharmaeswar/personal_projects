from rl_platform import environments, quality
from rl_platform.store import new_store


def _env_with_task(store):
    spec = {
        "name": "code-repair-env",
        "task_type": "code-repair",
        "observation_fields": ["code", "error"],
        "action_fields": ["edit", "run"],
        "reward": {"type": "dense", "min": -1, "max": 1},
    }
    env, _ = environments.register_environment(store, spec)
    task, _ = quality.create_task(store, env["id"], "Fix the failing test in this module.")
    return env, task


def good_scores(**over):
    scores = {"instruction_clarity": 5, "solvability": 5, "reward_correctness": 5,
              "no_leakage": 5, "coverage": 5}
    scores.update(over)
    return scores


def test_passing_review_approves_task():
    store = new_store()
    _, task = _env_with_task(store)
    review, errors = quality.review_task(store, task["id"], "rev-1", good_scores())
    assert errors == []
    assert review["verdict"] == "pass" and review["mean_score"] == 5.0
    assert store["tasks"][task["id"]]["status"] == "approved"


def test_low_item_score_fails_review():
    store = new_store()
    _, task = _env_with_task(store)
    review, _ = quality.review_task(store, task["id"], "rev-1", good_scores(reward_correctness=2))
    assert review["verdict"] == "needs_work"
    assert review["mean_score"] == 4.4


def test_low_mean_fails_review():
    store = new_store()
    _, task = _env_with_task(store)
    review, _ = quality.review_task(store, task["id"], "rev-1", good_scores(
        instruction_clarity=3, solvability=3, reward_correctness=3, no_leakage=3, coverage=3))
    assert review["verdict"] == "needs_work" and review["mean_score"] == 3.0


def test_missing_rubric_item_rejected():
    store = new_store()
    _, task = _env_with_task(store)
    review, errors = quality.review_task(store, task["id"], "rev-1", {"instruction_clarity": 5})
    assert review is None and any("missing rubric" in e for e in errors)


def test_score_out_of_range_rejected():
    store = new_store()
    _, task = _env_with_task(store)
    review, errors = quality.review_task(store, task["id"], "rev-1", good_scores(coverage=6))
    assert review is None and errors


def test_create_task_needs_instruction():
    store = new_store()
    env, _ = environments.register_environment(store, {
        "name": "e", "task_type": "dialogue", "observation_fields": ["text"],
        "action_fields": ["reply"], "reward": {"type": "sparse", "min": 0, "max": 1}})
    task, errors = quality.create_task(store, env["id"], "  ")
    assert task is None and errors


def test_task_quality_aggregates_reviews():
    store = new_store()
    _, task = _env_with_task(store)
    quality.review_task(store, task["id"], "rev-1", good_scores())
    quality.review_task(store, task["id"], "rev-2", good_scores(coverage=4))
    agg = quality.task_quality(task["id"], list(store["reviews"].values()))
    assert agg["review_count"] == 2
    assert agg["mean_score"] == 4.9
    assert agg["verdict"] == "pass"


def test_task_quality_unreviewed():
    store = new_store()
    _, task = _env_with_task(store)
    agg = quality.task_quality(task["id"], list(store["reviews"].values()))
    assert agg["verdict"] == "unreviewed" and agg["mean_score"] is None


def test_reviewer_agreement():
    store = new_store()
    _, task = _env_with_task(store)
    quality.review_task(store, task["id"], "rev-1", good_scores())
    quality.review_task(store, task["id"], "rev-2", good_scores())
    quality.review_task(store, task["id"], "rev-3", good_scores(reward_correctness=2))
    result = quality.reviewer_agreement(list(store["reviews"].values()))
    assert result["pairs"] == 3
    assert result["agreement_rate"] == 0.333


def test_reviewer_agreement_no_pairs():
    assert quality.reviewer_agreement([]) == {"pairs": 0, "agreement_rate": None}


def test_quarantine_defects_lists_failing_items():
    store = new_store()
    _, task = _env_with_task(store)
    quality.review_task(store, task["id"], "rev-1", good_scores(reward_correctness=2, no_leakage=1))
    defects = quality.quarantine_defects(store)
    assert len(defects) == 1
    assert defects[0]["failing_items"] == ["no_leakage", "reward_correctness"]
