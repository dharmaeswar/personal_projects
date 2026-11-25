"""Failover / DR drill planner: produces a step plan and a drill report."""

def build_drill_plan(primary="db-primary", replica="db-replica", rpo_minutes=15, rto_minutes=30):
    steps=[
        {"step":1,"action":"Verify latest backup checksum and manifest","target":primary},
        {"step":2,"action":"Check replication lag is within RPO","target":replica},
        {"step":3,"action":"Snapshot pre-drill health checks","target":primary},
        {"step":4,"action":"Promote replica to primary in drill mode","target":replica},
        {"step":5,"action":"Run smoke queries against promoted replica","target":replica},
        {"step":6,"action":"Verify application connection string failover","target":"app-tier"},
        {"step":7,"action":"Record timings against RTO and restore original topology","target":primary},
    ]
    return {"primary":primary,"replica":replica,"rpo_minutes":rpo_minutes,"rto_minutes":rto_minutes,"steps":steps}

def run_drill(plan, health_results):
    failed=[r.name for r in health_results if r.status=="fail"]
    ready = not failed
    return {"ready_for_drill":ready,"blocking_checks":failed,"steps_planned":len(plan["steps"]),
            "verdict":"PROCEED" if ready else "BLOCKED - fix failing health checks first",
            "rpo_minutes":plan["rpo_minutes"],"rto_minutes":plan["rto_minutes"]}
