"""Health checks over synthetic PostgreSQL metric snapshots."""
from dataclasses import dataclass

@dataclass
class CheckResult:
    name: str; status: str; value: float; threshold: str; detail: str

def check_snapshot(snap: dict) -> list:
    results=[]
    # connection saturation
    pct = snap["active_connections"]/snap["max_connections"]*100 if snap["max_connections"] else 0
    results.append(CheckResult("connection_saturation", "fail" if pct>=90 else "warn" if pct>=75 else "pass", round(pct,1), "<75 pass, 75-90 warn, >=90 fail", f"{snap['active_connections']}/{snap['max_connections']} connections"))
    lag = snap["replication_lag_seconds"]
    results.append(CheckResult("replication_lag", "fail" if lag>=60 else "warn" if lag>=10 else "pass", lag, "<10 pass, 10-60 warn, >=60 fail", f"lag {lag}s"))
    head = snap["wraparound_headroom_pct"]
    results.append(CheckResult("wraparound_headroom", "fail" if head<20 else "warn" if head<40 else "pass", head, ">=40 pass, 20-40 warn, <20 fail", f"headroom {head}%"))
    bloat = snap["bloat_ratio"]
    results.append(CheckResult("bloat_ratio", "fail" if bloat>=0.35 else "warn" if bloat>=0.20 else "pass", bloat, "<0.20 pass, 0.20-0.35 warn, >=0.35 fail", f"bloat {bloat}"))
    age = snap["backup_age_hours"]
    results.append(CheckResult("backup_freshness", "fail" if age>=48 else "warn" if age>=24 else "pass", age, "<24 pass, 24-48 warn, >=48 fail", f"last backup {age}h ago"))
    return results

def overall_status(results):
    if any(r.status=="fail" for r in results): return "fail"
    if any(r.status=="warn" for r in results): return "warn"
    return "pass"

SAMPLE_HEALTHY={"active_connections":42,"max_connections":200,"replication_lag_seconds":2,"wraparound_headroom_pct":78,"bloat_ratio":0.08,"backup_age_hours":6}
SAMPLE_DEGRADED={"active_connections":185,"max_connections":200,"replication_lag_seconds":75,"wraparound_headroom_pct":15,"bloat_ratio":0.42,"backup_age_hours":55}
