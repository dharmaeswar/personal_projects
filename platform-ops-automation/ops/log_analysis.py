"""Access-log analysis for the Platform Ops Automation demo project.

Parses synthetic access logs (one line per request), computes the per-minute
5xx error rate, and flags minutes where the rate exceeds a threshold.
Also provides percentile helpers for latency samples.

Log line format (common-log style, synthetic):
    2026-11-18T10:00:01Z GET / 200 0.042
    <ISO timestamp> <method> <path> <status> <latency seconds>
"""

import math
import random
import re
from collections import defaultdict
from datetime import datetime, timedelta

LOG_LINE = re.compile(
    r"^(?P<ts>\S+) (?P<method>\S+) (?P<path>\S+) "
    r"(?P<status>\d{3}) (?P<latency>\d+(?:\.\d+)?)$"
)


def parse_log_line(line):
    """Parse one log line. Returns a dict, or None for a malformed line."""
    match = LOG_LINE.match(line.strip())
    if not match:
        return None
    return {
        "timestamp": datetime.fromisoformat(match.group("ts").replace("Z", "+00:00")),
        "method": match.group("method"),
        "path": match.group("path"),
        "status": int(match.group("status")),
        "latency": float(match.group("latency")),
    }


def parse_log(text):
    """Parse a whole log. Malformed lines are skipped."""
    entries = []
    for line in text.splitlines():
        entry = parse_log_line(line)
        if entry is not None:
            entries.append(entry)
    return entries


def per_minute_error_rate(entries):
    """Group entries by minute; return {minute: (total, errors, rate)}."""
    by_minute = defaultdict(lambda: [0, 0])
    for entry in entries:
        minute = entry["timestamp"].replace(second=0, microsecond=0)
        by_minute[minute][0] += 1
        if entry["status"] >= 500:
            by_minute[minute][1] += 1
    return {
        minute: (total, errors, errors / total if total else 0.0)
        for minute, (total, errors) in sorted(by_minute.items())
    }


def flag_spike_minutes(entries, threshold=0.05):
    """Return the minutes whose 5xx rate is strictly above `threshold`.

    Default threshold: 5% of requests in a minute returning 5xx.
    """
    return [
        minute
        for minute, (_, _, rate) in per_minute_error_rate(entries).items()
        if rate > threshold
    ]


def percentile(samples, pct):
    """Nearest-rank percentile of a list of numbers (pct in 0-100).

    Returns None for an empty list.
    """
    if not samples:
        return None
    ordered = sorted(samples)
    rank = math.ceil(pct / 100.0 * len(ordered))
    rank = max(1, min(rank, len(ordered)))
    return ordered[rank - 1]


def p50(samples):
    return percentile(samples, 50)


def p95(samples):
    return percentile(samples, 95)


def generate_synthetic_log(seed=42, minutes=10, spike_minute=5, spike_rate=0.4):
    """Generate a synthetic access log.

    Most minutes are clean (all 200s); `spike_minute` has `spike_rate`
    of its requests returning 500. Returns the log as a string.
    """
    rng = random.Random(seed)
    start = datetime(2026, 11, 18, 10, 0, 0)
    lines = []
    for minute in range(minutes):
        count = rng.randint(40, 60)
        for i in range(count):
            ts = start + timedelta(minutes=minute, seconds=rng.randint(0, 59))
            is_error = minute == spike_minute and rng.random() < spike_rate
            status = 500 if is_error else 200
            latency = round(rng.uniform(0.3, 0.8) if is_error else rng.uniform(0.005, 0.12), 3)
            lines.append(
                f"{ts.strftime('%Y-%m-%dT%H:%M:%SZ')} GET / {status} {latency}"
            )
    return "\n".join(lines) + "\n"


def main():
    log_text = generate_synthetic_log()
    entries = parse_log(log_text)
    print(f"parsed {len(entries)} log lines")
    for minute, (total, errors, rate) in per_minute_error_rate(entries).items():
        print(f"{minute:%H:%M}  total={total} errors={errors} rate={rate:.1%}")
    spikes = flag_spike_minutes(entries)
    if spikes:
        print("flagged spike minutes:", [m.strftime("%H:%M") for m in spikes])
    else:
        print("no spike minutes found")
    latencies = [e["latency"] for e in entries]
    print(f"latency p50={p50(latencies):.3f}s p95={p95(latencies):.3f}s")


if __name__ == "__main__":
    main()
