from rl_platform import api, partner
from rl_platform.store import new_store


def good_spec(**over):
    spec = {
        "name": "tool-use-env",
        "task_type": "tool-use",
        "observation_fields": ["tool_output"],
        "action_fields": ["call_tool"],
        "reward": {"type": "dense", "min": -1, "max": 1},
    }
    spec.update(over)
    return spec


def good_rows():
    return [
        {"instruction": "Call the search tool.", "expected_action": "search", "label": "tool-use"},
        {"instruction": "Call the calculator.", "expected_action": "calculate", "label": "tool-use"},
    ]


def test_submit_and_test_passes():
    store = new_store()
    sub = partner.submit_environment(store, "partner-beta", good_spec(), good_rows())
    assert sub["status"] == "submitted"
    tested, errors = partner.test_submission(store, sub["id"])
    assert errors == [] and tested["status"] == "tested_pass"


def test_submit_fails_on_bad_rows():
    store = new_store()
    rows = [{"instruction": "Do it."}, {"instruction": "Do it.", "expected_action": "x"}]
    sub = partner.submit_environment(store, "partner-beta", good_spec(), rows)
    _, errors = partner.test_submission(store, sub["id"])
    assert any("missing fields" in e for e in errors)
    assert store["submissions"][sub["id"]]["status"] == "needs_changes"


def test_submit_fails_on_unlabelled_rows():
    store = new_store()
    rows = [
        {"instruction": "A", "expected_action": "x"},
        {"instruction": "B", "expected_action": "y"},
    ]
    _, errors = partner.test_submission(
        store, partner.submit_environment(store, "p", good_spec(), rows)["id"])
    assert any("fewer than half" in e for e in errors)


def test_iterate_then_approve():
    store = new_store()
    sub = partner.submit_environment(store, "partner-beta", good_spec(), [{"instruction": "Do it."}])
    partner.test_submission(store, sub["id"])
    assert sub["status"] == "needs_changes"
    updated, errors = partner.iterate_submission(store, sub["id"], good_spec(), good_rows())
    assert errors == [] and updated["version"] == 2 and updated["status"] == "submitted"
    partner.test_submission(store, sub["id"])
    approved, env, errors = partner.approve_submission(store, sub["id"])
    assert errors == [] and approved["status"] == "approved"
    assert env["name"] == "tool-use-env" and env["id"] in store["environments"]


def test_approve_requires_pass():
    store = new_store()
    sub = partner.submit_environment(store, "p", good_spec(), good_rows())
    _, _, errors = partner.approve_submission(store, sub["id"])
    assert errors


def test_iterate_requires_needs_changes():
    store = new_store()
    sub = partner.submit_environment(store, "p", good_spec(), good_rows())
    _, errors = partner.iterate_submission(store, sub["id"], good_spec(), good_rows())
    assert errors


def test_api_create_and_list_environments():
    store = new_store()
    status, env = api.handle(store, "POST", "/environments", good_spec())
    assert status == 201
    status, envs = api.handle(store, "GET", "/environments", {})
    assert status == 200 and len(envs) == 1


def test_api_create_environment_bad_request():
    store = new_store()
    status, payload = api.handle(store, "POST", "/environments", good_spec(task_type="nope"))
    assert status == 400 and payload["errors"]


def test_api_trajectory_flow_and_dashboard():
    store = new_store()
    _, env = api.handle(store, "POST", "/environments", good_spec())
    steps = [{"observation": "o", "action": "call_tool", "reward": 1, "done": True}]
    status, traj = api.handle(store, "POST", "/trajectories",
                              {"env_id": env["id"], "agent": "model-a", "steps": steps})
    assert status == 201
    status, trajs = api.handle(store, "GET", "/environments/%s/trajectories" % env["id"], {})
    assert status == 200 and len(trajs) == 1
    status, run = api.handle(store, "POST", "/evaluations",
                             {"env_id": env["id"], "model_name": "model-a", "reward_threshold": 1})
    assert status == 201 and run["pass_rate"] == 1.0
    status, dash = api.handle(store, "GET", "/dashboard", {"targets": {env["id"]: 5}})
    assert status == 200 and dash["counts"]["trajectories"] == 1


def test_api_invalid_trajectory_returns_422():
    store = new_store()
    _, env = api.handle(store, "POST", "/environments", good_spec())
    steps = [{"observation": "o", "action": "call_tool", "reward": 99, "done": True}]
    status, payload = api.handle(store, "POST", "/trajectories",
                                 {"env_id": env["id"], "agent": "m", "steps": steps})
    assert status == 422 and payload["errors"]


def test_api_unknown_route():
    store = new_store()
    status, payload = api.handle(store, "GET", "/nope", {})
    assert status == 404


def test_api_submission_and_review_flow():
    store = new_store()
    status, sub = api.handle(store, "POST", "/submissions",
                             {"partner": "p", "spec": good_spec(), "training_rows": good_rows()})
    assert status == 201
    status, tested = api.handle(store, "POST", "/submissions/%s/test" % sub["id"], {})
    assert status == 200 and tested["status"] == "tested_pass"
