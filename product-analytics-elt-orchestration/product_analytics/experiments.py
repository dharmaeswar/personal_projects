"""Experimentation guardrails: assignment, SRM, balance, and lift checks.

Product teams run A/B tests on top of the analytics warehouse, so the
pipeline validates each experiment before its readout is trusted:

- deterministic hash assignment (stable across re-runs, no RNG drift),
- sample-ratio-mismatch (SRM) check against the intended split,
- pre-period balance check: the arms must look the same *before* the
  experiment started, or the assignment is broken,
- post-period lift on the save rate with a two-proportion z-test.

A failed guardrail raises, so the DAG never publishes a catalog whose
experiment readouts are untrustworthy. Results are written to
``experiment_results`` so the daily report shows exactly what was
checked. All math is plain standard-library statistics; no scipy.
"""
from __future__ import annotations

import hashlib
import math
import sqlite3

DEFAULT_EXPERIMENT = "save_button_variant"
DEFAULT_VARIANTS = ("control", "treatment")
DEFAULT_WEIGHTS = (0.5, 0.5)

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiment_assignments (
    experiment TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    variant    TEXT NOT NULL,
    PRIMARY KEY (experiment, user_id)
);
CREATE TABLE IF NOT EXISTS experiment_results (
    check_name TEXT PRIMARY KEY,
    status     TEXT NOT NULL,
    detail     TEXT NOT NULL DEFAULT ''
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _hash_fraction(key: str) -> float:
    """Stable uniform fraction in [0, 1) for a string key (SHA-256)."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / 16**12


def assign_variant(user_id: str, experiment: str = DEFAULT_EXPERIMENT,
                   variants: tuple[str, ...] = DEFAULT_VARIANTS,
                   weights: tuple[float, ...] = DEFAULT_WEIGHTS,
                   seed: int = 42) -> str:
    """Deterministically assign one user to a variant by hash bucketing."""
    if len(variants) != len(weights) or not variants:
        raise ValueError("variants and weights must be non-empty and aligned")
    if abs(sum(weights) - 1.0) > 1e-9:
        raise ValueError("weights must sum to 1.0")
    fraction = _hash_fraction(f"{experiment}:{seed}:{user_id}")
    cumulative = 0.0
    for variant, weight in zip(variants, weights):
        cumulative += weight
        if fraction < cumulative:
            return variant
    return variants[-1]


def assign_users(conn: sqlite3.Connection, experiment: str = DEFAULT_EXPERIMENT,
                 variants: tuple[str, ...] = DEFAULT_VARIANTS,
                 weights: tuple[float, ...] = DEFAULT_WEIGHTS,
                 seed: int = 42) -> dict[str, int]:
    """Assign every staged user to a variant (idempotent). Returns counts."""
    ensure_schema(conn)
    users = [r[0] for r in conn.execute(
        "SELECT DISTINCT user_id FROM staged_events")]
    for user_id in users:
        conn.execute(
            "INSERT OR IGNORE INTO experiment_assignments (experiment, user_id, variant)"
            " VALUES (?, ?, ?)",
            (experiment, user_id, assign_variant(user_id, experiment, variants, weights, seed)),
        )
    conn.commit()
    rows = conn.execute(
        "SELECT variant, COUNT(*) FROM experiment_assignments WHERE experiment = ?"
        " GROUP BY variant",
        (experiment,),
    ).fetchall()
    return {variant: count for variant, count in rows}


def _gser(a: float, x: float) -> float:
    """Regularized lower incomplete gamma P(a, x), series form."""
    if x == 0:
        return 0.0
    ap = a
    total = 1.0 / a
    term = total
    for _ in range(1000):
        ap += 1
        term *= x / ap
        total += term
        if abs(term) < abs(total) * 1e-12:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a: float, x: float) -> float:
    """Regularized upper incomplete gamma Q(a, x), continued-fraction form."""
    tiny = 1e-300
    b = x + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-12:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_sf(statistic: float, dof: int) -> float:
    """Survival function P(Chi2_dof > statistic)."""
    if statistic <= 0:
        return 1.0
    a = dof / 2.0
    x = statistic / 2.0
    if x < a + 1:
        return 1.0 - _gser(a, x)
    return _gcf(a, x)


def srm_check(counts: dict[str, int], weights: tuple[float, ...] = DEFAULT_WEIGHTS,
              variants: tuple[str, ...] = DEFAULT_VARIANTS,
              alpha: float = 0.01) -> dict:
    """Chi-square SRM test: do the arm sizes match the intended split?"""
    total = sum(counts.values())
    if total == 0:
        return {"check": "srm", "status": "fail", "statistic": 0.0,
                "p_value": 0.0, "detail": "no users assigned"}
    if len(variants) != len(weights):
        raise ValueError("variants and weights must be aligned")
    counts = {v: counts.get(v, 0) for v in variants}
    expected = [total * w for w in weights]
    statistic = sum((counts[v] - e) ** 2 / e for v, e in zip(variants, expected))
    p_value = chi2_sf(statistic, len(variants) - 1)
    passed = p_value >= alpha
    detail = (f"arms {counts} vs expected split {weights}: "
              f"chi2={statistic:.2f}, p={p_value:.4f}")
    return {"check": "srm", "status": "pass" if passed else "fail",
            "statistic": statistic, "p_value": p_value, "detail": detail}


def _norm_sf(z: float) -> float:
    """Two-sided normal tail probability for |z|."""
    return math.erfc(abs(z) / math.sqrt(2.0))


def compare_proportions(success_a: int, n_a: int, success_b: int, n_b: int) -> dict:
    """Two-proportion z-test of arm B vs arm A. Returns lift, z, p, 95% CI."""
    if n_a == 0 or n_b == 0:
        raise ValueError("both arms need observations")
    p_a = success_a / n_a
    p_b = success_b / n_b
    pooled = (success_a + success_b) / (n_a + n_b)
    se_pooled = math.sqrt(max(pooled * (1 - pooled), 0.0) * (1 / n_a + 1 / n_b))
    z = (p_b - p_a) / se_pooled if se_pooled else 0.0
    p_value = _norm_sf(z)
    se_diff = math.sqrt(p_a * (1 - p_a) / n_a + p_b * (1 - p_b) / n_b)
    lift = p_b - p_a
    half = 1.96 * se_diff
    return {
        "rate_a": p_a, "rate_b": p_b, "lift": lift,
        "ci_low": lift - half, "ci_high": lift + half,
        "z": z, "p_value": p_value,
    }


def _save_rate(conn: sqlite3.Connection, experiment: str, variant: str,
               start: str | None, end: str | None) -> tuple[int, int]:
    """(users who saved at least once, active users) for one arm and window.

    Save rate is a per-user proportion — the share of active users who
    saved at least once — so it always stays in [0, 1]. A ``None`` bound
    means open-ended.
    """
    clauses = ["a.experiment = ?", "a.variant = ?"]
    params: list = [experiment, variant]
    if start is not None:
        clauses.append("s.event_date >= ?")
        params.append(start)
    if end is not None:
        clauses.append("s.event_date <= ?")
        params.append(end)
    where = " AND ".join(clauses)
    savers = conn.execute(
        f"SELECT COUNT(DISTINCT s.user_id) FROM staged_events s "
        f"JOIN experiment_assignments a ON s.user_id = a.user_id "
        f"WHERE {where} AND s.event_type = 'pin_save'",
        params,
    ).fetchone()[0]
    active = conn.execute(
        f"SELECT COUNT(DISTINCT s.user_id) FROM staged_events s "
        f"JOIN experiment_assignments a ON s.user_id = a.user_id "
        f"WHERE {where}",
        params,
    ).fetchone()[0]
    return savers, active


def run_experiment_checks(conn: sqlite3.Connection,
                          experiment: str = DEFAULT_EXPERIMENT,
                          start_date: str = "2026-11-08",
                          latest_date: str = "2026-11-14",
                          alpha: float = 0.01) -> list[dict]:
    """Run every guardrail for one experiment. Returns one row per check.

    Pre-period is every event before ``start_date``; post-period is
    ``start_date`` through ``latest_date``. Raises RuntimeError when a
    guardrail (SRM or pre-period balance) fails, so the DAG stops before
    publishing.
    """
    ensure_schema(conn)
    counts = assign_users(conn, experiment)
    checks: list[dict] = []

    srm = srm_check(counts, weights=DEFAULT_WEIGHTS, alpha=alpha)
    checks.append(srm)
    if srm["status"] == "fail":
        # Broken assignment: the arms themselves are wrong, so balance and
        # lift would compare against an empty arm. Record and stop here.
        _write_results(conn, checks)
        raise RuntimeError("experiment guardrails failed: ['srm']")

    pre_control = _save_rate(conn, experiment, "control", None, _day_before(start_date))
    pre_treatment = _save_rate(conn, experiment, "treatment", None, _day_before(start_date))
    pre = compare_proportions(pre_control[0], pre_control[1],
                              pre_treatment[0], pre_treatment[1])
    balance_passed = pre["p_value"] >= alpha
    checks.append({
        "check": "preperiod_balance",
        "status": "pass" if balance_passed else "fail",
        "detail": (f"pre-period save rate control={pre['rate_a']:.4f} "
                   f"treatment={pre['rate_b']:.4f} (n={pre_control[1]}/{pre_treatment[1]}), "
                   f"z={pre['z']:.2f}, p={pre['p_value']:.4f}"),
    })

    post_control = _save_rate(conn, experiment, "control", start_date, latest_date)
    post_treatment = _save_rate(conn, experiment, "treatment", start_date, latest_date)
    post = compare_proportions(post_control[0], post_control[1],
                               post_treatment[0], post_treatment[1])
    checks.append({
        "check": "postperiod_lift",
        "status": "pass",
        "detail": (f"post-period save rate control={post['rate_a']:.4f} "
                   f"treatment={post['rate_b']:.4f} (n={post_control[1]}/{post_treatment[1]}), "
                   f"lift={post['lift']:+.4f} 95% CI "
                   f"[{post['ci_low']:+.4f}, {post['ci_high']:+.4f}], "
                   f"z={post['z']:.2f}, p={post['p_value']:.4f}"),
    })

    _write_results(conn, checks)
    failed = [c["check"] for c in checks
              if c["status"] == "fail" and c["check"] in ("srm", "preperiod_balance")]
    if failed:
        raise RuntimeError(f"experiment guardrails failed: {failed}")
    return checks


def _write_results(conn: sqlite3.Connection, checks: list[dict]) -> None:
    for check in checks:
        conn.execute(
            "INSERT OR REPLACE INTO experiment_results (check_name, status, detail)"
            " VALUES (?, ?, ?)",
            (check["check"], check["status"], check["detail"]),
        )
    conn.commit()


def _day_before(date: str) -> str:
    """YYYY-MM-DD string for the day before ``date``."""
    from datetime import date as _date, timedelta

    year, month, day = (int(part) for part in date.split("-"))
    return (_date(year, month, day) - timedelta(days=1)).isoformat()
