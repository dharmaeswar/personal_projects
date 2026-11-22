"""Dashboards and observability: environment quality, collection progress,
evaluation results and pipeline health in one view.
"""

STALE_AFTER_SECONDS = 3600


def environment_quality(store):
    """Per-environment quality: review mean blended with trajectory validity."""
    from .quality import task_quality

    out = {}
    for env in store["environments"].values():
        tasks = [t for t in store["tasks"].values() if t["env_id"] == env["id"]]
        reviews = list(store["reviews"].values())
        means = [task_quality(t["id"], reviews)["mean_score"] for t in tasks]
        means = [m for m in means if m is not None]
        review_mean = round(sum(means) / len(means), 2) if means else None
        trajs = [t for t in store["trajectories"].values() if t["env_id"] == env["id"]]
        validity = round(sum(1 for t in trajs if t["valid"]) / len(trajs), 3) if trajs else None
        score = None
        if review_mean is not None and validity is not None:
            score = round(0.6 * (review_mean / 5.0) + 0.4 * validity, 3)
        elif review_mean is not None:
            score = round(review_mean / 5.0, 3)
        elif validity is not None:
            score = validity
        out[env["id"]] = {
            "name": env["name"],
            "task_type": env["task_type"],
            "status": env["status"],
            "review_mean": review_mean,
            "trajectory_validity": validity,
            "quality_score": score,
        }
    return out


def collection_progress(store, targets):
    """Collected vs target trajectories per environment."""
    out = {}
    for env_id, target in targets.items():
        collected = sum(1 for t in store["trajectories"].values() if t["env_id"] == env_id)
        out[env_id] = {
            "collected": collected,
            "target": target,
            "progress": round(collected / target, 3) if target else None,
            "remaining": max(target - collected, 0),
        }
    return out


def record_pipeline_event(store, feed, status, lag_seconds, error_count=0):
    event = {"feed": feed, "status": status, "lag_seconds": lag_seconds, "error_count": error_count}
    store["pipeline_events"].append(event)
    return event


def pipeline_health(store):
    """Per-feed health: error rate, worst lag, and feeds that look stale."""
    by_feed = {}
    for event in store["pipeline_events"]:
        agg = by_feed.setdefault(event["feed"], {"events": 0, "errors": 0, "max_lag": 0, "failed": 0})
        agg["events"] += 1
        agg["errors"] += event["error_count"]
        agg["max_lag"] = max(agg["max_lag"], event["lag_seconds"])
        if event["status"] != "ok":
            agg["failed"] += 1
    out = {}
    for feed, agg in by_feed.items():
        out[feed] = {
            "error_rate": round(agg["errors"] / agg["events"], 3) if agg["events"] else 0.0,
            "max_lag_seconds": agg["max_lag"],
            "stale": agg["max_lag"] > STALE_AFTER_SECONDS,
            "healthy": agg["failed"] == 0 and agg["max_lag"] <= STALE_AFTER_SECONDS,
        }
    return out


def dashboard(store, targets):
    """One combined view for the platform dashboard page."""
    return {
        "environment_quality": environment_quality(store),
        "collection_progress": collection_progress(store, targets),
        "pipeline_health": pipeline_health(store),
        "counts": {
            "environments": len(store["environments"]),
            "trajectories": len(store["trajectories"]),
            "tasks": len(store["tasks"]),
            "eval_runs": len(store["eval_runs"]),
        },
    }
