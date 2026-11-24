"""Batch processing control plane for the Platform Ops Automation
demo project.

Models the control plane that creates and fulfills background jobs
at scale (the shape of a system handling on the order of 100 million
jobs a day and growing): queue depth against capacity, creation
versus fulfillment throughput, stalled jobs, retry exhaustion, and
per-component fulfillment latency, plus headroom against a 10x
growth target. Plain dicts in, checks out. Demo data only — no real
job system is contacted, and no production batch-platform experience
is claimed.
"""

DEFAULT_MAX_QUEUE_DEPTH = 1_000_000
DEFAULT_MAX_STALLED_JOBS = 100
DEFAULT_MAX_RETRY_EXHAUSTED_PER_HOUR = 50
DEFAULT_MAX_FULFILL_P95_SECONDS = 300
GROWTH_TARGET = 10


def check_control_plane(state,
                        max_queue_depth=DEFAULT_MAX_QUEUE_DEPTH,
                        max_stalled_jobs=DEFAULT_MAX_STALLED_JOBS,
                        max_retry_exhausted_per_hour=DEFAULT_MAX_RETRY_EXHAUSTED_PER_HOUR,
                        max_fulfill_p95_seconds=DEFAULT_MAX_FULFILL_P95_SECONDS):
    """Check one control-plane snapshot. `state` is a dict with
    `queue_depth`, `queue_capacity`, `jobs_created_per_hour`,
    `jobs_fulfilled_per_hour`, `stalled_jobs`,
    `retry_exhausted_per_hour` and `components` (a list of dicts with
    `name` and `fulfill_p95_seconds`). Returns a list of check dicts
    with `name`, `status` ("pass"/"fail") and a human-readable
    `detail`."""
    checks = []
    checks.append(
        {
            "name": "queue-depth",
            "status": "pass"
            if state["queue_depth"] <= max_queue_depth
            else "fail",
            "detail": f"queue depth {state['queue_depth']:,} "
            f"(limit {max_queue_depth:,})",
        }
    )
    checks.append(
        {
            "name": "creation-vs-fulfillment",
            "status": "pass"
            if state["jobs_fulfilled_per_hour"]
            >= state["jobs_created_per_hour"]
            else "fail",
            "detail": f"created {state['jobs_created_per_hour']:,} / hour, "
            f"fulfilled {state['jobs_fulfilled_per_hour']:,} / hour",
        }
    )
    checks.append(
        {
            "name": "stalled-jobs",
            "status": "pass"
            if state["stalled_jobs"] <= max_stalled_jobs
            else "fail",
            "detail": f"{state['stalled_jobs']} stalled jobs "
            f"(limit {max_stalled_jobs})",
        }
    )
    checks.append(
        {
            "name": "retry-exhaustion",
            "status": "pass"
            if state["retry_exhausted_per_hour"]
            <= max_retry_exhausted_per_hour
            else "fail",
            "detail": f"{state['retry_exhausted_per_hour']} jobs exhausted "
            f"retries per hour (limit {max_retry_exhausted_per_hour})",
        }
    )
    for component in state["components"]:
        checks.append(
            {
                "name": f"fulfill-p95:{component['name']}",
                "status": "pass"
                if component["fulfill_p95_seconds"]
                <= max_fulfill_p95_seconds
                else "fail",
                "detail": f"{component['name']} fulfill p95 "
                f"{component['fulfill_p95_seconds']} s "
                f"(limit {max_fulfill_p95_seconds})",
            }
        )
    return checks


def control_plane_summary(state, growth_target=GROWTH_TARGET):
    """Aggregate one snapshot into a summary dict. `headroom_x` is how
    many times current fulfillment throughput the queue capacity
    supports at the current creation rate; `growth_ready` is True
    only when every check passes and headroom covers the growth
    target."""
    checks = check_control_plane(state)
    failed = [c for c in checks if c["status"] == "fail"]
    created = state["jobs_created_per_hour"]
    headroom = (
        state["queue_capacity"] / created if created else float("inf")
    )
    return {
        "queue_depth": state["queue_depth"],
        "queue_capacity": state["queue_capacity"],
        "jobs_created_per_hour": created,
        "jobs_fulfilled_per_hour": state["jobs_fulfilled_per_hour"],
        "stalled_jobs": state["stalled_jobs"],
        "headroom_x": round(headroom, 1),
        "checks_passed": len(checks) - len(failed),
        "checks_total": len(checks),
        "overall": "healthy" if not failed else "degraded",
        "growth_ready": not failed and headroom >= growth_target,
    }


def demo_state():
    """A synthetic snapshot at roughly 100M jobs a day: creation and
    fulfillment matched, but one component's fulfill p95 is over the
    limit, so the plane is degraded and not growth-ready."""
    return {
        "queue_depth": 420_000,
        "queue_capacity": 40_000_000,
        "jobs_created_per_hour": 4_200_000,
        "jobs_fulfilled_per_hour": 4_200_000,
        "stalled_jobs": 12,
        "retry_exhausted_per_hour": 8,
        "components": [
            {"name": "loan-payments", "fulfill_p95_seconds": 180},
            {"name": "escrow", "fulfill_p95_seconds": 240},
            {"name": "statements", "fulfill_p95_seconds": 420},
        ],
    }


def control_plane_report(state):
    """One-line-per-check text report for a synthetic snapshot."""
    summary = control_plane_summary(state)
    lines = [
        f"Batch control plane: {summary['overall']} "
        f"({summary['checks_passed']}/{summary['checks_total']} checks pass), "
        f"headroom {summary['headroom_x']}x, "
        f"growth-ready: {summary['growth_ready']}",
        f"Queue depth {summary['queue_depth']:,} / "
        f"{summary['queue_capacity']:,}; created "
        f"{summary['jobs_created_per_hour']:,} / hour, fulfilled "
        f"{summary['jobs_fulfilled_per_hour']:,} / hour; "
        f"{summary['stalled_jobs']} stalled jobs",
    ]
    for check in check_control_plane(state):
        mark = "PASS" if check["status"] == "pass" else "FAIL"
        lines.append(f"[{mark}] {check['name']}: {check['detail']}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(control_plane_report(demo_state()))
