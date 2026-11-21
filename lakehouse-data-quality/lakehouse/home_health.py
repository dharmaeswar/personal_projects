"""Home-health episode data quality: an ETL/ELT extension for the lakehouse.

A Data Engineer II in home health moves episode and visit records from
source systems into governed tables. This module models that flow with
synthetic, seeded data (no real patient data anywhere):

- **Episodes** — one row per home-health episode: de-identified patient
  key, start/end dates, discharge status, diagnosis group.
- **Visits** — one row per visit: visit id, episode id, visit date, visit
  type (nursing / therapy / aide), duration in minutes, clinician id.

Quality rules mirror the lakehouse checks: completeness, uniqueness,
ranges, referential integrity, plus a home-health rule — every visit
must fall inside its episode's start/end window. Bad visits are
quarantined with a reason instead of dropped silently, and the gold
table is an episode summary (visit count, total and average minutes)
built only from clean silver visits, so gold reconciles back to silver.

The fixture plants 9 bad rows on purpose so the checks have real
violations to catch:

- 2 duplicate visit_id values
- 2 null episode_id values
- 1 visit_date outside its episode window
- 1 negative duration_minutes value
- 1 episode_id that does not exist in the episodes table
- 1 episode whose end_date is before its start_date
- 1 visit with a duration over the 480-minute daily cap
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .checks import (
    CheckResult,
    check_completeness,
    check_ranges,
    check_referential_integrity,
    check_uniqueness,
)

MAX_VISIT_MINUTES = 480
MIN_EPISODE_DATE = pd.Timestamp("2026-01-01")
MAX_EPISODE_DATE = pd.Timestamp("2026-11-30")

VISIT_TYPES = ["nursing", "therapy", "aide"]
DIAGNOSIS_GROUPS = ["cardiac", "orthopedic", "respiratory", "diabetes", "wound"]
DISCHARGE_STATUSES = ["completed", "transferred", "ongoing"]


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def generate_episodes(seed: int = 42) -> pd.DataFrame:
    """40 synthetic home-health episodes, one row per episode."""
    rng = _rng(seed)
    n = 40
    starts = pd.to_datetime(
        rng.integers(
            MIN_EPISODE_DATE.value, pd.Timestamp("2026-10-01").value, size=n
        )
    )
    lengths = rng.integers(7, 61, size=n)
    episodes = pd.DataFrame(
        {
            "episode_id": [f"EP-{1000 + i}" for i in range(n)],
            "patient_key": [f"PT-{2000 + i}" for i in range(n)],
            "start_date": starts,
            "end_date": starts + pd.to_timedelta(lengths, unit="D"),
            "discharge_status": rng.choice(DISCHARGE_STATUSES, size=n),
            "diagnosis_group": rng.choice(DIAGNOSIS_GROUPS, size=n),
        }
    )
    return episodes


def generate_visits(episodes: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """~200 synthetic visits, each inside its episode's window."""
    rng = _rng(seed + 1)
    rows = []
    visit_no = 0
    for _, ep in episodes.iterrows():
        n_visits = int(rng.integers(3, 8))
        span = (ep["end_date"] - ep["start_date"]).days
        for _ in range(n_visits):
            visit_no += 1
            rows.append(
                {
                    "visit_id": f"V-{5000 + visit_no}",
                    "episode_id": ep["episode_id"],
                    "visit_date": ep["start_date"]
                    + pd.Timedelta(days=int(rng.integers(0, span + 1))),
                    "visit_type": str(rng.choice(VISIT_TYPES)),
                    "duration_minutes": int(rng.integers(15, 121)),
                    "clinician_id": f"CL-{int(rng.integers(100, 130))}",
                }
            )
    return pd.DataFrame(rows)


def plant_violations(
    visits: pd.DataFrame, episodes: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Plant 9 bad rows: 8 bad visits and 1 bad episode. Returns copies."""
    visits = visits.copy()
    episodes = episodes.copy()
    # 2 duplicate visit_ids (copy rows 0 and 1 with new index positions)
    dup = visits.iloc[[0, 1]].copy()
    visits = pd.concat([visits, dup], ignore_index=True)
    # 2 null episode_ids
    visits.loc[visits.index[2], "episode_id"] = None
    visits.loc[visits.index[3], "episode_id"] = None
    # 1 visit_date outside its episode window (push it past the end date)
    row = visits.iloc[4]
    ep_end = episodes.loc[
        episodes["episode_id"] == row["episode_id"], "end_date"
    ].iloc[0]
    visits.loc[visits.index[4], "visit_date"] = ep_end + pd.Timedelta(days=30)
    # 1 negative duration
    visits.loc[visits.index[5], "duration_minutes"] = -20
    # 1 unknown episode_id
    visits.loc[visits.index[6], "episode_id"] = "EP-9999"
    # 1 duration over the 480-minute cap
    visits.loc[visits.index[7], "duration_minutes"] = 600
    # 1 episode whose end_date is before its start_date (use the last
    # episode so it does not share visits with the out-of-window plant)
    episodes.loc[episodes.index[-1], "end_date"] = (
        episodes.loc[episodes.index[-1], "start_date"] - pd.Timedelta(days=5)
    )
    return visits, episodes


def generate_home_health(seed: int = 42) -> dict[str, pd.DataFrame]:
    """Seeded episodes + visits with the 9 planted violations."""
    episodes = generate_episodes(seed)
    visits = generate_visits(episodes, seed)
    visits, episodes = plant_violations(visits, episodes)
    return {"episodes": episodes, "visits": visits}


def check_visit_window(
    visits: pd.DataFrame, episodes: pd.DataFrame
) -> CheckResult:
    """Fail if any visit_date falls outside its episode's window."""
    window = episodes.set_index("episode_id")[["start_date", "end_date"]]
    # Episodes that end before they start are owned by the episode_dates
    # check; their visits are not double-counted here.
    valid_window = window[window["end_date"] >= window["start_date"]]
    failing: list[int] = []
    for idx, row in visits.iterrows():
        if pd.isna(row["episode_id"]) or row["episode_id"] not in valid_window.index:
            continue  # completeness / referential checks own those rows
        start = valid_window.loc[row["episode_id"], "start_date"]
        end = valid_window.loc[row["episode_id"], "end_date"]
        if not (start <= row["visit_date"] <= end):
            failing.append(int(idx))
    if not failing:
        return CheckResult(
            "visit_window", True, "all visits inside their episode window"
        )
    return CheckResult(
        "visit_window",
        False,
        f"{len(failing)} visits outside their episode window",
        failing,
    )


def check_episode_dates(episodes: pd.DataFrame) -> CheckResult:
    """Fail if any episode ends before it starts."""
    bad = episodes[episodes["end_date"] < episodes["start_date"]]
    if bad.empty:
        return CheckResult(
            "episode_dates", True, "all episodes end on or after they start"
        )
    return CheckResult(
        "episode_dates",
        False,
        f"{len(bad)} episodes end before they start",
        [int(i) for i in bad.index],
    )


def validate_episodes(episodes: pd.DataFrame) -> list[CheckResult]:
    """Completeness, uniqueness and date-order checks for episodes."""
    return [
        check_completeness(
            episodes, ["episode_id", "patient_key", "start_date", "end_date"]
        ),
        check_uniqueness(episodes, "episode_id"),
        check_episode_dates(episodes),
    ]


def validate_visits(
    visits: pd.DataFrame, episodes: pd.DataFrame
) -> list[CheckResult]:
    """All visit checks: completeness, uniqueness, ranges, refs, window."""
    return [
        check_completeness(visits, ["visit_id", "episode_id", "visit_date"]),
        check_uniqueness(visits, "visit_id"),
        check_ranges(visits, "duration_minutes", 0, MAX_VISIT_MINUTES),
        check_referential_integrity(visits, "episode_id", episodes, "episode_id"),
        check_visit_window(visits, episodes),
    ]


def quarantine_visits(
    visits: pd.DataFrame, episodes: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split visits into silver (clean) and quarantine (failed, with reason).

    A visit fails if it trips any visit check. Duplicate visit_ids keep
    only the first occurrence in silver.
    """
    checks = validate_visits(visits, episodes)
    reasons: dict[int, list[str]] = {}
    for result in checks:
        for row in result.failing_rows:
            reasons.setdefault(row, []).append(result.name)
    mask = pd.Series(False, index=visits.index)
    for row in reasons:
        mask.loc[row] = True
    quarantine = visits.loc[mask].copy()
    quarantine["quarantine_reason"] = [
        "; ".join(reasons[i]) for i in quarantine.index
    ]
    silver = visits.loc[~mask].copy()
    silver = silver.drop_duplicates(subset=["visit_id"], keep="first")
    return silver.reset_index(drop=True), quarantine.reset_index(drop=True)


def build_episode_summary(
    silver_visits: pd.DataFrame, episodes: pd.DataFrame
) -> pd.DataFrame:
    """Gold table: per-episode visit count and minutes, from silver only."""
    agg = (
        silver_visits.groupby("episode_id", as_index=False)
        .agg(
            visit_count=("visit_id", "count"),
            total_minutes=("duration_minutes", "sum"),
            avg_minutes=("duration_minutes", "mean"),
        )
    )
    agg["avg_minutes"] = agg["avg_minutes"].round(1)
    summary = agg.merge(
        episodes[["episode_id", "discharge_status", "diagnosis_group"]],
        on="episode_id",
        how="left",
    )
    return summary.sort_values("episode_id").reset_index(drop=True)
