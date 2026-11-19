"""Linux host bottleneck diagnosis for the Platform Ops Automation
demo project.

Applies the isolation method from the Systems Reliability Engineer
job description — "Identify bottlenecks (Is it CPU? IO?)" — to a plain
dict of synthetic host signals: CPU utilisation, IO wait, memory use,
load average and disk latency. Demo data only; no real host is
described and no production performance-tuning experience is claimed.
"""

CPU_HIGH_PCT = 85
IOWAIT_HIGH_PCT = 20
MEM_HIGH_PCT = 90
DISK_LATENCY_HIGH_MS = 50


def diagnose(signals):
    """Diagnose one host. `signals` has `cpu_util_pct`, `iowait_pct`,
    `mem_used_pct`, `load_1m`, `cpu_count`, `disk_latency_ms`.
    Returns a dict with `verdict` ("healthy", "cpu-bound",
    "io-bound", "memory-pressure" or "saturated"), an `evidence`
    list and a `next_check` suggestion."""
    evidence = []
    cpu = signals["cpu_util_pct"]
    iowait = signals["iowait_pct"]
    mem = signals["mem_used_pct"]
    load = signals["load_1m"]
    cores = signals["cpu_count"]
    disk_ms = signals["disk_latency_ms"]
    load_per_core = load / cores if cores else load

    if cpu >= CPU_HIGH_PCT:
        evidence.append(f"CPU utilisation {cpu}% (high: {CPU_HIGH_PCT}%)")
    if iowait >= IOWAIT_HIGH_PCT:
        evidence.append(f"IO wait {iowait}% (high: {IOWAIT_HIGH_PCT}%)")
    if mem >= MEM_HIGH_PCT:
        evidence.append(f"memory use {mem}% (high: {MEM_HIGH_PCT}%)")
    if disk_ms >= DISK_LATENCY_HIGH_MS:
        evidence.append(
            f"disk latency {disk_ms} ms (high: {DISK_LATENCY_HIGH_MS} ms)"
        )
    if load_per_core > 1.0:
        evidence.append(
            f"load {load} on {cores} cores "
            f"({load_per_core:.2f} per core, over 1.00)"
        )

    if mem >= MEM_HIGH_PCT:
        verdict = "memory-pressure"
        next_check = "check the largest memory consumers and swap use"
    elif iowait >= IOWAIT_HIGH_PCT or disk_ms >= DISK_LATENCY_HIGH_MS:
        verdict = "io-bound"
        next_check = "check disk queue depth and the slowest device"
    elif cpu >= CPU_HIGH_PCT or load_per_core > 1.0:
        verdict = "cpu-bound"
        next_check = "profile the hottest processes (flamegraph) and check run queue"
    else:
        verdict = "healthy"
        next_check = "no action; keep the baseline for comparison"
    return {"verdict": verdict, "evidence": evidence,
            "next_check": next_check}


def demo_signals(kind="healthy"):
    """Synthetic host signal presets for each verdict."""
    presets = {
        "healthy": {"cpu_util_pct": 42, "iowait_pct": 3, "mem_used_pct": 61,
                    "load_1m": 2.1, "cpu_count": 8, "disk_latency_ms": 4},
        "cpu": {"cpu_util_pct": 96, "iowait_pct": 4, "mem_used_pct": 58,
                "load_1m": 9.4, "cpu_count": 8, "disk_latency_ms": 5},
        "io": {"cpu_util_pct": 55, "iowait_pct": 38, "mem_used_pct": 63,
               "load_1m": 6.8, "cpu_count": 8, "disk_latency_ms": 120},
        "memory": {"cpu_util_pct": 48, "iowait_pct": 5, "mem_used_pct": 94,
                   "load_1m": 3.0, "cpu_count": 8, "disk_latency_ms": 6},
    }
    return dict(presets[kind])


def diagnosis_report(signals):
    """One short text report for a synthetic host."""
    result = diagnose(signals)
    lines = [f"Host verdict: {result['verdict']}"]
    for item in result["evidence"]:
        lines.append(f"  - {item}")
    if not result["evidence"]:
        lines.append("  - all signals within limits")
    lines.append(f"Next check: {result['next_check']}")
    return "\n".join(lines)


if __name__ == "__main__":
    for kind in ("healthy", "cpu", "io", "memory"):
        print(f"--- {kind} ---")
        print(diagnosis_report(demo_signals(kind)))
