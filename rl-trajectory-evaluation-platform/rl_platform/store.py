"""In-memory store for the RL trajectory evaluation platform.

All data is synthetic and local. The store is a plain dict of tables so the
service layer stays testable without a database server.
"""


def new_store():
    return {
        "environments": {},
        "trajectories": {},
        "tasks": {},
        "reviews": {},
        "eval_runs": {},
        "submissions": {},
        "pipeline_events": [],
        "seq": {"env": 0, "traj": 0, "task": 0, "review": 0, "run": 0, "sub": 0},
    }


def next_id(store, kind):
    store["seq"][kind] += 1
    return "%s-%04d" % (kind, store["seq"][kind])
