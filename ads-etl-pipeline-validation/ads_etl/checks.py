"""Data-quality checks for ad event data.

Every check returns a :class:`CheckResult` with a name, a pass/fail flag,
and the detail a reviewer needs (how many rows failed, and which ones).
Checks never raise on bad data — a failing check is a result, not an error.
Rows are plain dicts; ``failing_rows`` holds list positions in the input.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .data import MAX_EVENT_TS, MIN_EVENT_TS, WATERMARK_TS

TOLERANCE = 0.01


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    failing_rows: list[int] = field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - convenience only
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name}: {self.detail}"


def check_completeness(rows: list[dict], columns: list[str]) -> CheckResult:
    """Fail if any listed column holds nulls; report the null count per column."""
    parts = []
    failing: set[int] = set()
    for col in columns:
        nulls = [i for i, r in enumerate(rows) if r.get(col) is None]
        if nulls:
            parts.append(f"{col}: {len(nulls)} nulls")
            failing.update(nulls)
    if not parts:
        return CheckResult("completeness", True, "no nulls in checked columns")
    return CheckResult("completeness", False, "; ".join(parts), sorted(failing))


def check_uniqueness(rows: list[dict], column: str) -> CheckResult:
    """Fail if ``column`` holds duplicate values; report the extra (later) rows."""
    seen: dict = {}
    failing = []
    for i, r in enumerate(rows):
        value = r.get(column)
        if value in seen:
            failing.append(i)
        else:
            seen[value] = i
    if not failing:
        return CheckResult(
            f"uniqueness:{column}", True, f"all {len(rows)} values of {column} unique"
        )
    n_values = len({rows[i][column] for i in failing})
    return CheckResult(
        f"uniqueness:{column}",
        False,
        f"{n_values} duplicated {column} values ({len(failing)} extra rows)",
        failing,
    )


def check_ranges(
    rows: list[dict], column: str, low=None, high=None
) -> CheckResult:
    """Fail if any value in ``column`` falls outside [low, high]."""
    failing = []
    for i, r in enumerate(rows):
        value = r.get(column)
        if value is None:
            continue
        if (low is not None and value < low) or (high is not None and value > high):
            failing.append(i)
    if not failing:
        return CheckResult(f"range:{column}", True, f"all values of {column} in range")
    return CheckResult(
        f"range:{column}",
        False,
        f"{len(failing)} rows outside range for {column}",
        failing,
    )


def check_clicks_within_impressions(rows: list[dict]) -> CheckResult:
    """Fail if clicks exceed impressions on any row (impossible in real logs)."""
    failing = [
        i
        for i, r in enumerate(rows)
        if r.get("clicks") is not None
        and r.get("impressions") is not None
        and r["clicks"] > r["impressions"]
    ]
    if not failing:
        return CheckResult(
            "clicks_within_impressions", True, "clicks <= impressions on every row"
        )
    return CheckResult(
        "clicks_within_impressions",
        False,
        f"{len(failing)} rows where clicks > impressions",
        failing,
    )


def check_referential_integrity(
    rows: list[dict], column: str, reference: list[dict], reference_column: str
) -> CheckResult:
    """Fail if any non-null value in ``column`` is missing from the reference table."""
    ref_values = {r[reference_column] for r in reference if r.get(reference_column) is not None}
    failing = [
        i
        for i, r in enumerate(rows)
        if r.get(column) is not None and r[column] not in ref_values
    ]
    if not failing:
        return CheckResult(
            f"fk:{column}->{reference_column}",
            True,
            f"all {column} values found in {reference_column}",
        )
    return CheckResult(
        f"fk:{column}->{reference_column}",
        False,
        f"{len(failing)} rows with {column} not in {reference_column}",
        failing,
    )


def check_spend_arithmetic(rows: list[dict], tolerance: float = TOLERANCE) -> CheckResult:
    """Fail if spend_usd differs from clicks * cpc_usd by more than tolerance."""
    failing = []
    for i, r in enumerate(rows):
        if r.get("clicks") is None or r.get("cpc_usd") is None or r.get("spend_usd") is None:
            continue
        if abs(r["spend_usd"] - round(r["clicks"] * r["cpc_usd"], 2)) > tolerance:
            failing.append(i)
    if not failing:
        return CheckResult(
            "spend_arithmetic", True, "spend_usd equals clicks * cpc_usd on every row"
        )
    return CheckResult(
        "spend_arithmetic",
        False,
        f"{len(failing)} rows where spend_usd != clicks * cpc_usd",
        failing,
    )


def check_late_arriving(rows: list[dict]) -> CheckResult:
    """Report (never fail) how many rows arrived after the watermark.

    Late rows are valid data, not violations, so this check always passes;
    it exists so the report and monitoring can count them.
    """
    late = [i for i, r in enumerate(rows) if r.get("event_ts") is not None and r["event_ts"] < WATERMARK_TS]
    return CheckResult(
        "late_arriving",
        True,
        f"{len(late)} late-arriving rows (event_ts before watermark {WATERMARK_TS[:10]})",
        late,
    )


def check_reconciliation(
    silver: list[dict], gold: list[dict], tolerance: float = TOLERANCE
) -> CheckResult:
    """Fail if gold daily spend does not match silver spend grouped the same way."""
    from collections import defaultdict

    expected: dict[tuple, dict] = defaultdict(lambda: {"impressions": 0, "clicks": 0, "spend_usd": 0.0})
    campaign_channel = {}
    for r in silver:
        key = (r["event_ts"][:10], r["campaign_id"])
        expected[key]["impressions"] += r["impressions"]
        expected[key]["clicks"] += r["clicks"]
        expected[key]["spend_usd"] = round(expected[key]["spend_usd"] + r["spend_usd"], 2)
    got = {
        (g["event_date"], g["campaign_id"]): g
        for g in gold
    }
    problems = []
    for key in set(expected) | set(got):
        if key not in got:
            problems.append(f"gold group missing for {key}")
        elif key not in expected:
            problems.append(f"unexpected gold group for {key}")
        else:
            e, g = expected[key], got[key]
            if e["impressions"] != g["impressions"] or e["clicks"] != g["clicks"]:
                problems.append(f"wrong impressions/clicks for {key}")
            if abs(e["spend_usd"] - g["spend_usd"]) > tolerance:
                problems.append(f"wrong spend_usd for {key}")
    if not problems:
        return CheckResult(
            "reconciliation",
            True,
            f"gold matches silver on all {len(expected)} daily campaign groups",
        )
    return CheckResult("reconciliation", False, "; ".join(problems))


def run_all_checks(
    events: list[dict], ads: list[dict], campaigns: list[dict]
) -> list[CheckResult]:
    """Run the full bronze check suite on the events table."""
    return [
        check_completeness(events, ["event_id", "ad_id", "campaign_id", "event_ts"]),
        check_uniqueness(events, "event_id"),
        check_ranges(events, "impressions", low=0),
        check_ranges(events, "clicks", low=0),
        check_ranges(events, "spend_usd", low=0),
        check_clicks_within_impressions(events),
        check_ranges(events, "event_ts", low=MIN_EVENT_TS, high=MAX_EVENT_TS),
        check_referential_integrity(events, "ad_id", ads, "ad_id"),
        check_referential_integrity(events, "campaign_id", campaigns, "campaign_id"),
        check_spend_arithmetic(events),
    ]
