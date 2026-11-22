"""Partner workflow: submit an environment plus training data, test it,
iterate on failures, and approve it for the platform.

A submission is accepted only when the environment spec validates and the
training data passes its checks (required fields, labelled rows, coverage
across task types). Failures send the submission back with a concrete list
of what to fix; the partner iterates by submitting a new version.
"""

REQUIRED_TRAINING_FIELDS = {"instruction", "expected_action"}


def submit_environment(store, partner, spec, training_rows):
    from .store import next_id

    sub_id = next_id(store, "sub")
    submission = {
        "id": sub_id,
        "partner": partner,
        "spec": spec,
        "training_rows": training_rows,
        "version": spec.get("version", 1),
        "status": "submitted",
        "test_results": None,
    }
    store["submissions"][sub_id] = submission
    return submission


def test_training_rows(rows):
    """Check partner training data: fields, labels, coverage, duplicates."""
    errors = []
    if not isinstance(rows, list) or not rows:
        return ["training data must be a non-empty list of rows"]
    seen = set()
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append("row %d must be an object" % i)
            continue
        missing = REQUIRED_TRAINING_FIELDS - set(row.keys())
        if missing:
            errors.append("row %d missing fields: %s" % (i, ", ".join(sorted(missing))))
        key = (row.get("instruction"), row.get("expected_action"))
        if key in seen:
            errors.append("row %d duplicates an earlier row" % i)
        seen.add(key)
        if row.get("label") is not None and not isinstance(row["label"], str):
            errors.append("row %d label must be text" % i)
    labelled = sum(1 for r in rows if isinstance(r, dict) and r.get("label"))
    if rows and labelled < len(rows) / 2:
        errors.append("fewer than half of rows carry a label (%d of %d)" % (labelled, len(rows)))
    return errors


def test_submission(store, submission_id):
    """Run spec validation and training-data checks; pass or needs_changes."""
    from .environments import validate_environment_spec

    submission = store["submissions"].get(submission_id)
    if submission is None:
        return None, ["submission %s not found" % submission_id]
    errors = validate_environment_spec(submission["spec"])
    errors += test_training_rows(submission["training_rows"])
    submission["test_results"] = {"passed": not errors, "errors": errors}
    submission["status"] = "tested_pass" if not errors else "needs_changes"
    return submission, errors


def iterate_submission(store, submission_id, spec, training_rows):
    """Partner fixes the flagged issues and resubmits as a new version."""
    submission = store["submissions"].get(submission_id)
    if submission is None:
        return None, ["submission %s not found" % submission_id]
    if submission["status"] != "needs_changes":
        return None, ["only a needs_changes submission can be iterated"]
    submission["spec"] = spec
    submission["training_rows"] = training_rows
    submission["version"] = submission.get("version", 1) + 1
    submission["status"] = "submitted"
    submission["test_results"] = None
    return submission, []


def approve_submission(store, submission_id):
    """Approve a passing submission and register its environment."""
    from .environments import register_environment

    submission = store["submissions"].get(submission_id)
    if submission is None:
        return None, None, ["submission %s not found" % submission_id]
    if submission["status"] != "tested_pass":
        return None, None, ["submission must pass tests before approval"]
    env, errors = register_environment(store, submission["spec"])
    if errors:
        return None, None, errors
    submission["status"] = "approved"
    submission["environment_id"] = env["id"]
    return submission, env, []
