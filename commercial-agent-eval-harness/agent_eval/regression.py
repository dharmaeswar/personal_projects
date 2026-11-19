"""Regression check: compare a fresh eval run against a stored baseline.

A regression is any of: lower pass rate, a case that passed in the baseline
and fails now, or latency/cost growth beyond the allowed tolerance. The
comparison is per case id, so a renamed case shows up as added/removed
rather than silently passing.
"""

from __future__ import annotations

import json

DEFAULT_LATENCY_TOLERANCE_PCT = 10.0
DEFAULT_COST_TOLERANCE_PCT = 10.0


def load_baseline(path):
    with open(path) as fh:
        return json.load(fh)


def compare(baseline, current, latency_tol_pct=DEFAULT_LATENCY_TOLERANCE_PCT,
            cost_tol_pct=DEFAULT_COST_TOLERANCE_PCT):
    """Return a verdict dict comparing current results with the baseline."""
    base_cases = {c["case_id"]: c for c in baseline.get("cases", [])}
    cur_cases = {c["case_id"]: c for c in current.get("cases", [])}
    regressions = []
    improvements = []
    for case_id, cur in cur_cases.items():
        base = base_cases.get(case_id)
        if base is None:
            regressions.append(f"new case with no baseline: {case_id}")
            continue
        if base["passed"] and not cur["passed"]:
            regressions.append(
                f"{case_id}: passed in baseline, fails now "
                f"({'; '.join(cur['failures'])})")
        if not base["passed"] and cur["passed"]:
            improvements.append(f"{case_id}: failed in baseline, passes now")
        lat_growth = _pct_change(base.get("latency_ms", 0), cur.get("latency_ms", 0))
        if lat_growth > latency_tol_pct:
            regressions.append(
                f"{case_id}: latency up {lat_growth:.1f}% "
                f"({base.get('latency_ms')}ms -> {cur.get('latency_ms')}ms)")
        cost_growth = _pct_change(base.get("cost_usd", 0), cur.get("cost_usd", 0))
        if cost_growth > cost_tol_pct:
            regressions.append(
                f"{case_id}: cost up {cost_growth:.1f}% "
                f"(${base.get('cost_usd')} -> ${cur.get('cost_usd')})")
    for case_id in base_cases:
        if case_id not in cur_cases:
            regressions.append(f"case missing from current run: {case_id}")
    base_rate = baseline.get("pass_rate", 0)
    cur_rate = current.get("pass_rate", 0)
    verdict = "PASS" if not regressions else "REGRESSION"
    return {"verdict": verdict,
            "baseline_pass_rate": base_rate,
            "current_pass_rate": cur_rate,
            "pass_rate_delta": round(cur_rate - base_rate, 4),
            "regressions": regressions,
            "improvements": improvements}


def _pct_change(old, new):
    if old == 0:
        return 0.0 if new == 0 else 100.0
    return (new - old) / old * 100.0
