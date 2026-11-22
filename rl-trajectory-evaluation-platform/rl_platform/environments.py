"""Environment registry: browse, register and version RL environments.

An environment is the thing a partner submits and a research team trains
against: a task type, an observation/action schema and a reward spec. Only
validated specs can move from draft to review.
"""

TASK_TYPES = {"web-navigation", "code-repair", "math-reasoning", "tool-use", "dialogue"}
REWARD_TYPES = {"sparse", "dense", "shaped"}
STATUSES = {"draft", "in_review", "approved", "deprecated"}


def validate_environment_spec(spec):
    """Return a list of validation errors; empty means the spec is valid."""
    errors = []
    if not isinstance(spec, dict):
        return ["spec must be an object"]
    if not spec.get("name") or not str(spec["name"]).strip():
        errors.append("name is required")
    if spec.get("task_type") not in TASK_TYPES:
        errors.append("task_type must be one of %s" % sorted(TASK_TYPES))
    for field in ("observation_fields", "action_fields"):
        value = spec.get(field)
        if not isinstance(value, list) or not value or not all(isinstance(v, str) and v.strip() for v in value):
            errors.append("%s must be a non-empty list of field names" % field)
    reward = spec.get("reward")
    if not isinstance(reward, dict):
        errors.append("reward spec is required")
    else:
        if reward.get("type") not in REWARD_TYPES:
            errors.append("reward.type must be one of %s" % sorted(REWARD_TYPES))
        low, high = reward.get("min"), reward.get("max")
        if not isinstance(low, (int, float)) or not isinstance(high, (int, float)) or low >= high:
            errors.append("reward.min must be a number below reward.max")
    version = spec.get("version", 1)
    if not isinstance(version, int) or version < 1:
        errors.append("version must be a positive integer")
    return errors


def register_environment(store, spec):
    """Validate and register a new environment in draft status."""
    from .store import next_id

    errors = validate_environment_spec(spec)
    if errors:
        return None, errors
    env_id = next_id(store, "env")
    env = {
        "id": env_id,
        "name": spec["name"],
        "task_type": spec["task_type"],
        "observation_fields": list(spec["observation_fields"]),
        "action_fields": list(spec["action_fields"]),
        "reward": dict(spec["reward"]),
        "version": spec.get("version", 1),
        "status": "draft",
        "owner": spec.get("owner", "unknown"),
    }
    store["environments"][env_id] = env
    return env, []


def list_environments(store, task_type=None, status=None, owner=None):
    """Browse environments, optionally filtered; newest first by id."""
    envs = list(store["environments"].values())
    if task_type is not None:
        envs = [e for e in envs if e["task_type"] == task_type]
    if status is not None:
        envs = [e for e in envs if e["status"] == status]
    if owner is not None:
        envs = [e for e in envs if e["owner"] == owner]
    return sorted(envs, key=lambda e: e["id"], reverse=True)


def set_environment_status(store, env_id, status):
    if env_id not in store["environments"]:
        return None, ["environment %s not found" % env_id]
    if status not in STATUSES:
        return None, ["status must be one of %s" % sorted(STATUSES)]
    store["environments"][env_id]["status"] = status
    return store["environments"][env_id], []


def deprecate_environment(store, env_id):
    return set_environment_status(store, env_id, "deprecated")
