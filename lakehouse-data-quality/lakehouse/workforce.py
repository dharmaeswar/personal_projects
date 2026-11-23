"""Workforce Solutions data architecture: hiring, mobility and engagement.

An Amazon Workforce Solutions (WS) Data Engineer III owns the data
architecture behind hiring processes, career mobility and workforce
engagement for WW Stores, AWS, Devices and Talent Acquisition. This
module models that flow with synthetic, seeded data (no real employee
or company data anywhere), reusing the talent domains from
:mod:`lakehouse.talent` for roles and employees:

- **Streaming ingest** — hiring change events (requisition, candidate,
  interview, offer updates) arrive as micro-batches and are processed
  exactly once by reusing :func:`lakehouse.streaming.run_stream`:
  dedup on ``event_id`` against a checkpoint, late events dropped at
  the watermark. In production this is Kinesis / FireHose into
  Redshift; here it runs locally with pandas, and the code says so.
- **Batch ingest** — a nightly engagement-survey batch, deduplicated
  on ``survey_id`` (keep first), the way a Glue ETL job would load it.
- **Unified workforce model** — one row per requisition: the hiring
  funnel (candidates, interviews, offers, hires), time to fill, and
  offer-accept rate. Built only from clean (silver) rows.
- **Vended views** — an analytics view (per-department requisitions,
  hires, average time to fill, offer-accept rate, average engagement,
  internal moves) and an operational view (one row per requisition:
  funnel counts and status) for downstream integrations.
- **Quality checks** — completeness, uniqueness, score ranges,
  referential integrity, plus three workforce rules: no interview may
  predate the candidate's application, no offer may exist for a
  candidate with no interview, and no internal move may predate the
  employee's hire date. Bad rows are quarantined with a reason, never
  dropped silently.
- **GenAI-assist evaluation** — the JD asks the engineer to evaluate
  when a generative AI integration could automate a manual validation
  step. The evaluation here scores a deterministic, seeded stand-in
  rule proposer (no real LLM call is made, and the code says so)
  against the planted violations: precision and recall of the rules it
  proposes. A human stays in the loop: only rules that pass the
  evaluation are adopted.
- **Query tuning** — an inefficient per-requisition scan loop versus a
  single grouped aggregation, with measured wall times.

The fixture plants 8 bad rows on purpose so the checks have real
violations to catch:

- 2 duplicate candidate ``candidate_id`` values
- 1 null ``req_id`` on a candidate
- 1 candidate for an unknown requisition (REQ-999)
- 1 interview dated before the candidate applied
- 1 offer for a candidate with no interview
- 1 internal move effective before the employee's hire date
- 1 engagement survey with a score of 7 (valid range is 1-5)
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .checks import (
    CheckResult,
    check_completeness,
    check_ranges,
    check_referential_integrity,
    check_uniqueness,
)
from .streaming import run_stream
from .talent import generate_employees, generate_roles

SOURCES = ["Referral", "Job board", "Internal", "Agency"]
STAGES = ["applied", "screen", "interview", "offer", "hired", "rejected"]
QUARTERS = ["2026-Q1", "2026-Q2"]

N_REQUISITIONS = 15
N_CANDIDATES_BASE = 90
N_MOVES = 12
N_ENGAGEMENT_BASE = 120

# The rule proposer suggests these 8 candidate validation rules. Five of
# them match real workforce rules in this module; three are spurious
# (they sound plausible but match no real violation type). The evaluation
# scores the proposer against the 7 planted violation types.
PROPOSED_RULES = [
    ("interview_after_application", True),
    ("offer_needs_interview", True),
    ("move_after_hire", True),
    ("engagement_score_range", True),
    ("candidate_req_reference", True),
    ("flag_candidates_with_many_interviews", False),
    ("flag_requisitions_open_over_90_days", False),
    ("flag_engagement_score_exactly_3", False),
]

# The 7 violation types planted in the fixture.
VIOLATION_TYPES = [
    "duplicate_candidate",
    "null_req_id",
    "unknown_req",
    "early_interview",
    "offer_without_interview",
    "move_before_hire",
    "bad_engagement_score",
]


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def generate_requisitions(roles: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """15 requisitions, each on a role, opened Jan-Jun 2026."""
    rng = _rng(seed + 10)
    opened = pd.to_datetime(
        rng.integers(
            pd.Timestamp("2026-01-05").value,
            pd.Timestamp("2026-06-30").value,
            size=N_REQUISITIONS,
        )
    )
    statuses = rng.choice(
        ["open", "filled", "filled", "cancelled"], size=N_REQUISITIONS
    )
    closed = []
    for i, (o, s) in enumerate(zip(opened, statuses)):
        if s == "open":
            closed.append(pd.NaT)
        else:
            closed.append(o + pd.Timedelta(days=int(rng.integers(20, 90))))
    return pd.DataFrame(
        {
            "req_id": [f"REQ-{3001 + i}" for i in range(N_REQUISITIONS)],
            "role_id": rng.choice(roles["role_id"].tolist(), size=N_REQUISITIONS),
            "department": rng.choice(
                ["Engineering", "Data", "People Ops", "Finance", "Product"],
                size=N_REQUISITIONS,
            ),
            "opened_date": opened,
            "closed_date": pd.to_datetime(closed),
            "status": statuses,
        }
    )


def generate_candidates(
    requisitions: pd.DataFrame, seed: int = 42
) -> pd.DataFrame:
    """90 synthetic candidates spread across the requisitions."""
    rng = _rng(seed + 11)
    req_ids = requisitions["req_id"].tolist()
    opened_by_req = requisitions.set_index("req_id")["opened_date"]
    rows = []
    for i in range(N_CANDIDATES_BASE):
        req = str(rng.choice(req_ids))
        applied = opened_by_req.loc[req] + pd.Timedelta(
            days=int(rng.integers(0, 45))
        )
        rows.append(
            {
                "candidate_id": f"CAND-{4001 + i}",
                "req_id": req,
                "source": str(rng.choice(SOURCES)),
                "applied_date": applied,
                "stage": str(
                    rng.choice(
                        STAGES, p=[0.25, 0.2, 0.2, 0.1, 0.1, 0.15]
                    )
                ),
            }
        )
    return pd.DataFrame(rows)


def generate_interviews(
    candidates: pd.DataFrame, seed: int = 42
) -> pd.DataFrame:
    """Interviews only for candidates past the screen stage (~120 rows)."""
    rng = _rng(seed + 12)
    pool = candidates[
        candidates["stage"].isin(["interview", "offer", "hired"])
    ].reset_index(drop=True)
    applied_by_cand = candidates.set_index("candidate_id")["applied_date"]
    rows = []
    n = 0
    for _, cand in pool.iterrows():
        for round_no in range(1, int(rng.integers(1, 4)) + 1):
            n += 1
            rows.append(
                {
                    "interview_id": f"INT-{5001 + n - 1}",
                    "candidate_id": cand["candidate_id"],
                    "round": round_no,
                    "score": int(rng.integers(40, 101)),
                    "outcome": str(rng.choice(["pass", "fail"], p=[0.7, 0.3])),
                    "interview_date": applied_by_cand.loc[cand["candidate_id"]]
                    + pd.Timedelta(days=int(rng.integers(3, 30))),
                }
            )
    return pd.DataFrame(rows)


def generate_offers(candidates: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Offers only for candidates in offer/hired stage (~25 rows)."""
    rng = _rng(seed + 13)
    pool = candidates[
        candidates["stage"].isin(["offer", "hired"])
    ].reset_index(drop=True)
    rows = []
    for i, (_, cand) in enumerate(pool.iterrows()):
        rows.append(
            {
                "offer_id": f"OFF-{6001 + i}",
                "candidate_id": cand["candidate_id"],
                "status": (
                    "accepted" if cand["stage"] == "hired" else str(
                        rng.choice(["accepted", "declined", "pending"])
                    )
                ),
                "offer_date": cand["applied_date"]
                + pd.Timedelta(days=int(rng.integers(15, 60))),
            }
        )
    return pd.DataFrame(rows)


def generate_moves(
    employees: pd.DataFrame, roles: pd.DataFrame, seed: int = 42
) -> pd.DataFrame:
    """12 internal moves: an employee changes role after their hire date."""
    rng = _rng(seed + 14)
    hire_by_emp = employees.set_index("employee_id")["hire_date"]
    chosen = rng.choice(employees["employee_id"].tolist(), size=N_MOVES, replace=False)
    role_ids = roles["role_id"].tolist()
    rows = []
    for i, emp in enumerate(chosen):
        hire = hire_by_emp.loc[emp]
        rows.append(
            {
                "move_id": f"MOVE-{7001 + i}",
                "employee_id": emp,
                "from_role_id": str(rng.choice(role_ids)),
                "to_role_id": str(rng.choice(role_ids)),
                "effective_date": hire
                + pd.Timedelta(days=int(rng.integers(30, 400))),
            }
        )
    return pd.DataFrame(rows)


def generate_engagement(
    employees: pd.DataFrame, seed: int = 42
) -> pd.DataFrame:
    """120 engagement surveys: 60 employees x 2 quarters, scores 1-5."""
    rng = _rng(seed + 15)
    rows = []
    n = 0
    for emp in employees["employee_id"]:
        for quarter in QUARTERS:
            n += 1
            rows.append(
                {
                    "survey_id": f"SURV-{8001 + n - 1}",
                    "employee_id": emp,
                    "quarter": quarter,
                    "score": int(rng.integers(1, 6)),
                }
            )
    return pd.DataFrame(rows)


def plant_violations(
    candidates: pd.DataFrame,
    interviews: pd.DataFrame,
    offers: pd.DataFrame,
    moves: pd.DataFrame,
    engagement: pd.DataFrame,
    employees: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Plant 8 bad rows: 4 bad candidates, 1 bad interview, 1 bad offer,
    1 bad move, 1 bad survey. Returns copies."""
    candidates = candidates.copy()
    interviews = interviews.copy()
    offers = offers.copy()
    moves = moves.copy()
    engagement = engagement.copy()
    # 2 duplicate candidate_ids (copies of rows 0 and 1).
    dup = candidates.iloc[[0, 1]].copy()
    candidates = pd.concat([candidates, dup], ignore_index=True)
    # 1 null req_id.
    candidates.loc[candidates.index[2], "req_id"] = None
    # 1 candidate for an unknown requisition.
    candidates.loc[candidates.index[3], "req_id"] = "REQ-999"
    # 1 interview dated before the candidate applied.
    cand = candidates.iloc[4]
    interviews.loc[interviews.index[0], "candidate_id"] = cand["candidate_id"]
    interviews.loc[interviews.index[0], "interview_date"] = (
        cand["applied_date"] - pd.Timedelta(days=5)
    )
    # 1 offer for a candidate with no interview.
    interviewed = set(interviews["candidate_id"])
    no_interview = candidates[
        ~candidates["candidate_id"].isin(interviewed)
    ].iloc[0]
    offers.loc[offers.index[0], "candidate_id"] = no_interview["candidate_id"]
    # 1 internal move effective before the employee's hire date.
    hire = employees.loc[
        employees["employee_id"] == moves.iloc[0]["employee_id"], "hire_date"
    ].iloc[0]
    moves.loc[moves.index[0], "effective_date"] = hire - pd.Timedelta(days=30)
    # 1 engagement survey with a score of 7 (valid range is 1-5).
    engagement.loc[engagement.index[0], "score"] = 7
    return candidates, interviews, offers, moves, engagement


def generate_workforce(seed: int = 42) -> dict[str, pd.DataFrame]:
    """Seeded workforce domains with the 8 planted violations."""
    roles = generate_roles(seed)
    employees = generate_employees(roles, seed)
    requisitions = generate_requisitions(roles, seed)
    candidates = generate_candidates(requisitions, seed)
    interviews = generate_interviews(candidates, seed)
    offers = generate_offers(candidates, seed)
    moves = generate_moves(employees, roles, seed)
    engagement = generate_engagement(employees, seed)
    candidates, interviews, offers, moves, engagement = plant_violations(
        candidates, interviews, offers, moves, engagement, employees
    )
    return {
        "roles": roles,
        "employees": employees,
        "requisitions": requisitions,
        "candidates": candidates,
        "interviews": interviews,
        "offers": offers,
        "moves": moves,
        "engagement": engagement,
    }


def check_interview_after_application(
    interviews: pd.DataFrame, candidates: pd.DataFrame
) -> CheckResult:
    """Fail if any interview predates the candidate's application date."""
    applied_by_cand = candidates.set_index("candidate_id")["applied_date"]
    failing: list[int] = []
    for idx, row in interviews.iterrows():
        if pd.isna(row["candidate_id"]) or row["candidate_id"] not in applied_by_cand.index:
            continue  # completeness / referential checks own those rows
        if row["interview_date"] < applied_by_cand.loc[row["candidate_id"]]:
            failing.append(int(idx))
    if not failing:
        return CheckResult(
            "interview_after_application",
            True,
            "all interviews on or after application",
        )
    return CheckResult(
        "interview_after_application",
        False,
        f"{len(failing)} interviews dated before application",
        failing,
    )


def check_offer_has_interview(
    offers: pd.DataFrame, interviews: pd.DataFrame
) -> CheckResult:
    """Fail if any offer names a candidate with no interview on record."""
    interviewed = set(interviews["candidate_id"])
    failing = [
        int(idx)
        for idx, row in offers.iterrows()
        if pd.notna(row["candidate_id"]) and row["candidate_id"] not in interviewed
    ]
    if not failing:
        return CheckResult(
            "offer_has_interview", True, "every offer has an interview"
        )
    return CheckResult(
        "offer_has_interview",
        False,
        f"{len(failing)} offers for candidates with no interview",
        failing,
    )


def check_move_after_hire(
    moves: pd.DataFrame, employees: pd.DataFrame
) -> CheckResult:
    """Fail if any internal move predates the employee's hire date."""
    hire_by_emp = employees.set_index("employee_id")["hire_date"]
    failing: list[int] = []
    for idx, row in moves.iterrows():
        if pd.isna(row["employee_id"]) or row["employee_id"] not in hire_by_emp.index:
            continue  # completeness / referential checks own those rows
        if row["effective_date"] < hire_by_emp.loc[row["employee_id"]]:
            failing.append(int(idx))
    if not failing:
        return CheckResult(
            "move_after_hire", True, "all moves on or after hire"
        )
    return CheckResult(
        "move_after_hire",
        False,
        f"{len(failing)} moves effective before hire",
        failing,
    )


def validate_candidates(
    candidates: pd.DataFrame, requisitions: pd.DataFrame
) -> list[CheckResult]:
    """Completeness, uniqueness and requisition-reference checks."""
    return [
        check_completeness(candidates, ["candidate_id", "req_id", "applied_date"]),
        check_uniqueness(candidates, "candidate_id"),
        check_referential_integrity(candidates, "req_id", requisitions, "req_id"),
    ]


def validate_interviews(
    interviews: pd.DataFrame, candidates: pd.DataFrame
) -> list[CheckResult]:
    """Completeness, uniqueness, candidate reference, application rule."""
    return [
        check_completeness(interviews, ["interview_id", "candidate_id", "interview_date"]),
        check_uniqueness(interviews, "interview_id"),
        check_referential_integrity(interviews, "candidate_id", candidates, "candidate_id"),
        check_interview_after_application(interviews, candidates),
    ]


def validate_offers(
    offers: pd.DataFrame, candidates: pd.DataFrame, interviews: pd.DataFrame
) -> list[CheckResult]:
    """Completeness, uniqueness, candidate reference, interview rule."""
    return [
        check_completeness(offers, ["offer_id", "candidate_id", "offer_date"]),
        check_uniqueness(offers, "offer_id"),
        check_referential_integrity(offers, "candidate_id", candidates, "candidate_id"),
        check_offer_has_interview(offers, interviews),
    ]


def validate_moves(
    moves: pd.DataFrame, employees: pd.DataFrame, roles: pd.DataFrame
) -> list[CheckResult]:
    """Completeness, uniqueness, employee/role references, hire rule."""
    return [
        check_completeness(moves, ["move_id", "employee_id", "effective_date"]),
        check_uniqueness(moves, "move_id"),
        check_referential_integrity(moves, "employee_id", employees, "employee_id"),
        check_referential_integrity(moves, "to_role_id", roles, "role_id"),
        check_move_after_hire(moves, employees),
    ]


def validate_engagement(
    engagement: pd.DataFrame, employees: pd.DataFrame
) -> list[CheckResult]:
    """Completeness, uniqueness, employee reference, score range 1-5."""
    return [
        check_completeness(engagement, ["survey_id", "employee_id", "score"]),
        check_uniqueness(engagement, "survey_id"),
        check_referential_integrity(engagement, "employee_id", employees, "employee_id"),
        check_ranges(engagement, "score", 1, 5),
    ]


def _quarantine(
    frame: pd.DataFrame, checks: list[CheckResult], key: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a frame into silver (clean) and quarantine (failed, with reason).

    A row fails if it trips any check. Duplicate keys keep only the
    first occurrence in silver.
    """
    reasons: dict[int, list[str]] = {}
    for result in checks:
        for row in result.failing_rows:
            reasons.setdefault(row, []).append(result.name)
    mask = pd.Series(False, index=frame.index)
    for row in reasons:
        mask.loc[row] = True
    quarantine = frame.loc[mask].copy()
    quarantine["quarantine_reason"] = [
        "; ".join(reasons[i]) for i in quarantine.index
    ]
    silver = frame.loc[~mask].copy()
    silver = silver.drop_duplicates(subset=[key], keep="first")
    return silver.reset_index(drop=True), quarantine.reset_index(drop=True)


def quarantine_candidates(
    candidates: pd.DataFrame, requisitions: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _quarantine(candidates, validate_candidates(candidates, requisitions), "candidate_id")


def quarantine_interviews(
    interviews: pd.DataFrame, candidates: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _quarantine(interviews, validate_interviews(interviews, candidates), "interview_id")


def quarantine_offers(
    offers: pd.DataFrame, candidates: pd.DataFrame, interviews: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _quarantine(offers, validate_offers(offers, candidates, interviews), "offer_id")


def quarantine_moves(
    moves: pd.DataFrame, employees: pd.DataFrame, roles: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _quarantine(moves, validate_moves(moves, employees, roles), "move_id")


def quarantine_engagement(
    engagement: pd.DataFrame, employees: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _quarantine(engagement, validate_engagement(engagement, employees), "survey_id")


def build_unified_model(
    silver_requisitions: pd.DataFrame,
    roles: pd.DataFrame,
    silver_candidates: pd.DataFrame,
    silver_interviews: pd.DataFrame,
    silver_offers: pd.DataFrame,
) -> pd.DataFrame:
    """Hiring funnel per requisition: one row per clean requisition.

    Candidates, interviews, offers and hires counted from silver rows
    only; time to fill is closed minus opened for filled requisitions,
    and offer-accept rate is accepted offers over all offers.
    Candidates whose requisition failed validation cannot be counted:
    they are held back with their requisition.
    """
    cand = silver_candidates[
        silver_candidates["req_id"].isin(set(silver_requisitions["req_id"]))
    ]
    cand_counts = cand.groupby("req_id", as_index=False).agg(
        candidates=("candidate_id", "count"),
        hires=("stage", lambda s: int((s == "hired").sum())),
    )
    int_counts = (
        cand.merge(
            silver_interviews[["interview_id", "candidate_id"]],
            on="candidate_id",
            how="left",
        )
        .groupby("req_id", as_index=False)
        .agg(interviews=("interview_id", "count"))
    )
    off_counts = (
        cand.merge(
            silver_offers[["offer_id", "candidate_id", "status"]],
            on="candidate_id",
            how="left",
        )
        .groupby("req_id", as_index=False)
        .agg(
            offers=("offer_id", "count"),
            accepted_offers=("status", lambda s: int((s == "accepted").sum())),
        )
    )
    unified = silver_requisitions.merge(
        roles[["role_id", "role_title"]], on="role_id", how="left"
    )
    unified = unified.merge(cand_counts, on="req_id", how="left")
    unified = unified.merge(int_counts, on="req_id", how="left")
    unified = unified.merge(off_counts, on="req_id", how="left")
    for col in ["candidates", "hires", "interviews", "offers", "accepted_offers"]:
        unified[col] = unified[col].fillna(0).astype("int64")
    unified["time_to_fill_days"] = (
        (unified["closed_date"] - unified["opened_date"]).dt.days
    ).where(unified["status"] == "filled")
    unified["offer_accept_rate"] = (
        unified["accepted_offers"] / unified["offers"]
    ).round(2)
    return unified.sort_values("req_id").reset_index(drop=True)


def build_analytics_view(
    unified: pd.DataFrame,
    silver_engagement: pd.DataFrame,
    silver_moves: pd.DataFrame,
    employees: pd.DataFrame,
) -> pd.DataFrame:
    """Gold analytics view: one row per department.

    Requisitions, hires, average time to fill, offer-accept rate,
    average engagement score and internal moves — the numbers a
    Workforce Solutions team would chart. Engagement and moves are
    attributed to a department through the employee's current role.
    """
    view = (
        unified.groupby("department", as_index=False)
        .agg(
            requisitions=("req_id", "count"),
            hires=("hires", "sum"),
            avg_time_to_fill=("time_to_fill_days", "mean"),
            offers=("offers", "sum"),
            accepted_offers=("accepted_offers", "sum"),
        )
    )
    view["avg_time_to_fill"] = view["avg_time_to_fill"].round(1)
    view["offer_accept_rate"] = (
        view["accepted_offers"] / view["offers"]
    ).round(2)
    # Engagement per department: join surveys to employees to roles.
    # One department per role (first requisition for that role) so no
    # employee row is duplicated by the join.
    dept_by_emp = employees.merge(
        unified[["role_id", "department"]]
        .drop_duplicates(subset=["role_id"], keep="first"),
        left_on="role_id",
        right_on="role_id",
        how="left",
        suffixes=("", "_req"),
    )
    eng = silver_engagement.merge(
        dept_by_emp[["employee_id", "department"]],
        on="employee_id",
        how="left",
    )
    eng_by_dept = (
        eng.groupby("department", as_index=False)
        .agg(avg_engagement=("score", "mean"))
        .round(2)
    )
    view = view.merge(eng_by_dept, on="department", how="left")
    moves = silver_moves.merge(
        dept_by_emp[["employee_id", "department"]],
        on="employee_id",
        how="left",
    )
    moves_by_dept = (
        moves.groupby("department", as_index=False)
        .agg(internal_moves=("move_id", "count"))
    )
    view = view.merge(moves_by_dept, on="department", how="left")
    view["internal_moves"] = view["internal_moves"].fillna(0).astype("int64")
    return view.sort_values("department").reset_index(drop=True)


def build_operational_view(unified: pd.DataFrame) -> pd.DataFrame:
    """Gold operational view: one row per requisition, for downstream use.

    Current funnel counts, status and time to fill — the fields a
    hiring service reads to decide where a requisition stands.
    """
    return unified[
        [
            "req_id",
            "role_title",
            "department",
            "status",
            "candidates",
            "interviews",
            "offers",
            "hires",
            "time_to_fill_days",
            "offer_accept_rate",
        ]
    ].copy()


def check_unified_reconciliation(
    unified: pd.DataFrame,
    silver_candidates: pd.DataFrame,
    analytics_view: pd.DataFrame,
) -> CheckResult:
    """Fail if the vended views disagree with the unified model or silver."""
    vendable = silver_candidates[
        silver_candidates["req_id"].isin(set(unified["req_id"]))
    ]
    problems = []
    if int(unified["candidates"].sum()) != len(vendable):
        problems.append("unified candidate counts do not sum to silver candidates")
    if int(unified["hires"].sum()) != int(
        (vendable["stage"] == "hired").sum()
    ):
        problems.append("unified hires do not sum to silver hired candidates")
    if int(analytics_view["requisitions"].sum()) != len(unified):
        problems.append("analytics requisitions do not sum to unified rows")
    if int(analytics_view["hires"].sum()) != int(unified["hires"].sum()):
        problems.append("analytics hires do not match unified model")
    if problems:
        return CheckResult("workforce_reconciliation", False, "; ".join(problems))
    return CheckResult(
        "workforce_reconciliation",
        True,
        f"views reconcile: {len(unified)} requisitions, "
        f"{len(vendable)} vendable candidates",
    )


def generate_workforce_events(n: int = 120, seed: int = 42) -> pd.DataFrame:
    """Synthetic hiring change-event stream with planted late events and duplicates.

    120 events: 3 are duplicate deliveries of earlier event ids, 2 arrive
    with an event time older than the watermark will allow (late data).
    Duplicates are re-delivered in a later micro-batch than their
    originals, so the exactly-once dedup sees them as re-deliveries.
    Each event names its domain (requisition / candidate / interview /
    offer) and the requisition it concerns, the way a service log event
    would.
    """
    from datetime import datetime, timedelta, timezone

    rng = _rng(seed + 20)
    base = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)
    event_times = [base + timedelta(minutes=int(m)) for m in rng.integers(0, 600, size=n)]
    event_times.sort()
    df = pd.DataFrame(
        {
            "offset": list(range(n)),
            "event_id": [f"W{i:05d}" for i in range(n)],
            "event_time": pd.to_datetime(event_times, utc=True),
            "ingested_at": pd.to_datetime(
                [t + timedelta(seconds=int(s)) for t, s in zip(event_times, rng.integers(5, 120, size=n))],
                utc=True,
            ),
            "domain": rng.choice(["requisition", "candidate", "interview", "offer"], size=n),
            "req_id": [f"REQ-{3001 + int(i)}" for i in rng.integers(0, 15, size=n)],
            "event_type": rng.choice(["created", "updated", "completed"], size=n),
        }
    )
    dupes = df.iloc[[5, 40, 90]].copy()
    dupes["offset"] = [n, n + 1, n + 2]
    late = df.iloc[[10, 60]].copy()
    late["event_id"] = ["W90001", "W90002"]
    late["offset"] = [n + 3, n + 4]
    late["event_time"] = pd.to_datetime(
        [base - timedelta(hours=3), base - timedelta(hours=2, minutes=30)], utc=True
    )
    stream = pd.concat([df, dupes, late], ignore_index=True)
    return stream.sort_values("offset").reset_index(drop=True)


def run_workforce_stream(events: pd.DataFrame) -> dict:
    """Process the hiring event stream exactly once via the shared streamer."""
    return run_stream(events)


def load_engagement_batch(
    engagement: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Nightly batch load: dedup on survey_id, keep first; return (loaded, duplicates)."""
    dup_mask = engagement.duplicated(subset=["survey_id"], keep="first")
    duplicates = engagement.loc[dup_mask].copy().reset_index(drop=True)
    loaded = engagement.loc[~dup_mask].copy().reset_index(drop=True)
    return loaded, duplicates


def evaluate_genai_assist() -> dict:
    """Score the deterministic rule proposer against the planted violations.

    This is a stand-in evaluation, not a real LLM call: the proposer is
    a fixed seeded list of candidate validation rules (see
    ``PROPOSED_RULES``). Precision is the share of proposed rules that
    match a real workforce rule; recall is the share of the 7 planted
    violation types a proposed rule would catch. A rule is adopted only
    if the evaluation passes it — a human stays in the loop, the way
    the JD's responsible-AI practice requires.
    """
    proposed_true = [name for name, real in PROPOSED_RULES if real]
    proposed_all = [name for name, _ in PROPOSED_RULES]
    rule_to_violation = {
        "interview_after_application": "early_interview",
        "offer_needs_interview": "offer_without_interview",
        "move_after_hire": "move_before_hire",
        "engagement_score_range": "bad_engagement_score",
        "candidate_req_reference": "unknown_req",
    }
    caught = {rule_to_violation[name] for name in proposed_true}
    precision = round(len(proposed_true) / len(proposed_all), 3)
    recall = round(len(caught & set(VIOLATION_TYPES)) / len(VIOLATION_TYPES), 3)
    return {
        "rules_proposed": len(proposed_all),
        "rules_true": len(proposed_true),
        "violation_types": len(VIOLATION_TYPES),
        "violation_types_caught": len(caught & set(VIOLATION_TYPES)),
        "precision": precision,
        "recall": recall,
        "spurious_rules_rejected": len(proposed_all) - len(proposed_true),
        "real_llm_call": False,
    }


def tune_query_demo(
    silver_candidates: pd.DataFrame, silver_requisitions: pd.DataFrame
) -> dict:
    """Inefficient query vs tuned query, with measured wall times.

    Slow query (the anti-pattern): for each requisition, scan the whole
    candidate table to compute that requisition's average days from
    opening to application — one full pass per requisition, the way a
    row-by-row lookup behaves.
    Tuned query: a single group-by aggregation over the same data.
    Both must return identical per-requisition averages. The demo tiles
    the candidate table to at least 50k rows so the difference is
    measurable; the tiling only repeats seeded rows with new candidate
    ids, so the averages are unchanged.
    """
    import math

    reps = max(1, math.ceil(50000 / max(len(silver_candidates), 1)))
    big = pd.concat([silver_candidates] * reps, ignore_index=True)
    big["candidate_id"] = [f"CAND-{90000 + i}" for i in range(len(big))]
    opened = silver_requisitions.set_index("req_id")["opened_date"]
    big["days_to_apply"] = (
        big["applied_date"] - big["req_id"].map(opened)
    ).dt.days
    req_ids = silver_requisitions["req_id"].tolist()

    start = time.perf_counter()
    slow = {}
    for req in req_ids:
        subset = big[big["req_id"] == req]
        slow[req] = round(float(subset["days_to_apply"].mean()), 4) if len(subset) else None
    slow_ms = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    grouped = big.groupby("req_id")["days_to_apply"].mean().round(4)
    fast_ms = (time.perf_counter() - start) * 1000
    fast = {req: (None if req not in grouped.index else float(grouped.loc[req])) for req in req_ids}

    matches = all(
        (slow[r] is None and fast[r] is None)
        or (slow[r] is not None and fast[r] is not None and abs(slow[r] - fast[r]) < 0.001)
        for r in req_ids
    )
    return {
        "rows": len(big),
        "requisitions": len(req_ids),
        "slow_ms": round(slow_ms, 1),
        "fast_ms": round(fast_ms, 1),
        "speedup": round(slow_ms / fast_ms, 1) if fast_ms > 0 else float("inf"),
        "results_match": matches,
    }
