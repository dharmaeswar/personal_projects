"""Intelligent Talent Acquisition (ITA) candidate-funnel pipeline.

An Amazon ITA Data team builds the foundational data infrastructure
that powers hiring decisions: secure, scalable pipelines that turn raw
recruiting events into trusted, governed funnel data. This module
models that flow with synthetic, seeded data (no real candidate or
company data anywhere):

- **Streaming ingest** — candidate application events (applied,
  assessed, interviewed, offered, hired) arrive as micro-batches and
  are processed exactly once by reusing
  :func:`lakehouse.streaming.run_stream`: dedup on ``event_id``
  against a checkpoint, late events dropped at the watermark. In
  production this is Kinesis into Redshift; here it runs locally
  with pandas, and the code says so.
- **Batch ingest** — a nightly online-assessment batch (the kind of
  feed behind the 6M+ assessments ITA delivers a year), deduplicated
  on ``assessment_id`` (keep first), the way a Glue ETL job would
  load it.
- **Candidate-funnel model** — one row per clean application: the
  requisition and department, the candidate, the furthest stage
  reached, assessment score, interview count, offer and hire flags,
  and days from application to hire. Built only from silver rows.
- **Vended views** — a funnel view (per-department conversion at
  each stage: assessment, interview, offer, hire) and a requisition
  view (one row per requisition: applications, hires, fill rate,
  median days to hire) for downstream analytics.
- **Quality checks** — completeness, uniqueness, score ranges,
  referential integrity, and two recruiting rules: every interview
  must fall on or after the application date, and every hire must
  trace to an offer. Bad rows are quarantined with a reason, never
  dropped silently.

The fixture plants 8 bad rows on purpose so the checks have real
violations to catch:

- 2 duplicate application ``application_id`` values
- 2 null ``candidate_id`` values in applications
- 1 application for an unknown candidate (CAND-9999)
- 1 interview dated before the application date
- 1 assessment score outside 0-100
- 1 offer for an unknown requisition (REQ-999)
- 1 hire with no matching offer
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
from .streaming import run_stream

DEPARTMENTS = ["Engineering", "Data", "People Ops", "Finance", "Product"]

LOCATIONS = ["Seattle", "Arlington", "Remote", "Austin", "Nashville"]

ASSESSMENT_TYPES = ["Coding", "Work Sample", "Behavioral", "Aptitude"]

INTERVIEW_TYPES = ["Phone Screen", "Technical", "Behavioral", "Loop"]

N_REQUISITIONS = 30
N_CANDIDATES = 200
N_APPLICATIONS_BASE = 300


def _rng(seed: int = 42):
    import numpy as np

    return np.random.default_rng(seed)


def generate_requisitions(seed: int = 42) -> pd.DataFrame:
    """30 synthetic requisitions across 5 departments and 5 locations."""
    rng = _rng(seed)
    titles = [
        "Data Engineer", "Software Engineer", "Data Scientist",
        "Recruiter", "Program Manager", "Business Analyst",
        "ML Engineer", "Financial Analyst", "Product Manager",
        "Analytics Engineer",
    ]
    return pd.DataFrame(
        {
            "req_id": [f"REQ-{1001 + i}" for i in range(N_REQUISITIONS)],
            "title": [titles[i % len(titles)] for i in range(N_REQUISITIONS)],
            "department": rng.choice(DEPARTMENTS, size=N_REQUISITIONS),
            "location": rng.choice(LOCATIONS, size=N_REQUISITIONS),
            "open_date": pd.to_datetime(
                rng.integers(
                    pd.Timestamp("2026-01-01").value,
                    pd.Timestamp("2026-09-01").value,
                    size=N_REQUISITIONS,
                )
            ),
            "headcount": rng.integers(1, 6, size=N_REQUISITIONS),
        }
    )


def generate_candidates(seed: int = 42) -> pd.DataFrame:
    """200 synthetic candidates, each with a source channel."""
    rng = _rng(seed + 1)
    return pd.DataFrame(
        {
            "candidate_id": [f"CAND-{2001 + i}" for i in range(N_CANDIDATES)],
            "source": rng.choice(
                ["Referral", "Job Board", "University", "Agency", "Internal"],
                size=N_CANDIDATES,
            ),
            "years_experience": rng.integers(0, 16, size=N_CANDIDATES),
        }
    )


def generate_applications(
    requisitions: pd.DataFrame, candidates: pd.DataFrame, seed: int = 42
) -> pd.DataFrame:
    """300 synthetic applications, each dated on or after its req opened."""
    rng = _rng(seed + 2)
    open_by_req = requisitions.set_index("req_id")["open_date"]
    rows = []
    for i in range(N_APPLICATIONS_BASE):
        req = str(rng.choice(requisitions["req_id"].tolist()))
        opened = open_by_req.loc[req]
        max_days = max((pd.Timestamp("2026-11-01") - opened).days, 1)
        rows.append(
            {
                "application_id": f"APP-{30001 + i}",
                "req_id": req,
                "candidate_id": str(rng.choice(candidates["candidate_id"].tolist())),
                "applied_date": opened + pd.Timedelta(days=int(rng.integers(0, max_days))),
            }
        )
    return pd.DataFrame(rows)


def generate_assessments(
    applications: pd.DataFrame, seed: int = 42
) -> pd.DataFrame:
    """One online assessment for ~70% of applications, scored 0-100."""
    rng = _rng(seed + 3)
    rows = []
    for _, app in applications.iterrows():
        if rng.random() < 0.7:
            rows.append(
                {
                    "assessment_id": f"ASM-{40001 + len(rows)}",
                    "application_id": app["application_id"],
                    "assessment_type": str(rng.choice(ASSESSMENT_TYPES)),
                    "score": int(rng.integers(40, 101)),
                    "completed_date": app["applied_date"]
                    + pd.Timedelta(days=int(rng.integers(0, 8))),
                }
            )
    return pd.DataFrame(rows)


def generate_interviews(
    applications: pd.DataFrame, assessments: pd.DataFrame, seed: int = 42
) -> pd.DataFrame:
    """Interviews for ~45% of assessed applications, 1-3 rounds each."""
    rng = _rng(seed + 4)
    assessed = set(assessments["application_id"])
    rows = []
    for _, app in applications.iterrows():
        if app["application_id"] in assessed and rng.random() < 0.65:
            for round_no in range(1, int(rng.integers(1, 4)) + 1):
                rows.append(
                    {
                        "interview_id": f"INT-{50001 + len(rows)}",
                        "application_id": app["application_id"],
                        "interview_type": str(rng.choice(INTERVIEW_TYPES)),
                        "round_no": round_no,
                        "interview_date": app["applied_date"]
                        + pd.Timedelta(days=int(rng.integers(3, 22))),
                        "outcome": str(rng.choice(["Pass", "Fail"], p=[0.6, 0.4])),
                    }
                )
    return pd.DataFrame(rows)


def generate_offers(
    applications: pd.DataFrame, interviews: pd.DataFrame, seed: int = 42
) -> pd.DataFrame:
    """Offers for ~55% of applications with a passed interview."""
    rng = _rng(seed + 5)
    passed = set(
        interviews.loc[interviews["outcome"] == "Pass", "application_id"]
    )
    rows = []
    for _, app in applications.iterrows():
        if app["application_id"] in passed and rng.random() < 0.55:
            rows.append(
                {
                    "offer_id": f"OFR-{60001 + len(rows)}",
                    "application_id": app["application_id"],
                    "req_id": app["req_id"],
                    "offer_date": app["applied_date"]
                    + pd.Timedelta(days=int(rng.integers(10, 30))),
                    "salary": int(rng.integers(80000, 180001)),
                    "accepted": bool(rng.random() < 0.8),
                }
            )
    return pd.DataFrame(rows)


def generate_hires(offers: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """One hire row per accepted offer, with a start date after the offer."""
    rng = _rng(seed + 6)
    accepted = offers[offers["accepted"]]
    rows = []
    for _, offer in accepted.iterrows():
        rows.append(
            {
                "hire_id": f"HIR-{70001 + len(rows)}",
                "offer_id": offer["offer_id"],
                "application_id": offer["application_id"],
                "start_date": offer["offer_date"]
                + pd.Timedelta(days=int(rng.integers(7, 45))),
            }
        )
    return pd.DataFrame(rows)


def plant_violations(
    applications: pd.DataFrame,
    assessments: pd.DataFrame,
    interviews: pd.DataFrame,
    offers: pd.DataFrame,
    hires: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Plant 8 bad rows across the funnel tables. Returns copies."""
    applications = applications.copy()
    assessments = assessments.copy()
    interviews = interviews.copy()
    offers = offers.copy()
    hires = hires.copy()
    # 2 duplicate application_ids (copies of rows 0 and 1).
    dup = applications.iloc[[0, 1]].copy()
    applications = pd.concat([applications, dup], ignore_index=True)
    # 2 null candidate_ids.
    applications.loc[applications.index[2], "candidate_id"] = None
    applications.loc[applications.index[3], "candidate_id"] = None
    # 1 application for an unknown candidate.
    applications.loc[applications.index[4], "candidate_id"] = "CAND-9999"
    # 1 interview dated before the application date.
    row = interviews.iloc[0]
    app_date = applications.loc[
        applications["application_id"] == row["application_id"], "applied_date"
    ].iloc[0]
    interviews.loc[interviews.index[0], "interview_date"] = app_date - pd.Timedelta(days=5)
    # 1 assessment score outside 0-100.
    assessments.loc[assessments.index[0], "score"] = 142
    # 1 offer for an unknown requisition.
    offers.loc[offers.index[0], "req_id"] = "REQ-999"
    # 1 hire with no matching offer (offer_id that does not exist).
    hires.loc[hires.index[0], "offer_id"] = "OFR-99999"
    return {
        "applications": applications,
        "assessments": assessments,
        "interviews": interviews,
        "offers": offers,
        "hires": hires,
    }


def generate_recruiting(seed: int = 42) -> dict[str, pd.DataFrame]:
    """Seeded recruiting domains with the 8 planted violations."""
    requisitions = generate_requisitions(seed)
    candidates = generate_candidates(seed)
    applications = generate_applications(requisitions, candidates, seed)
    assessments = generate_assessments(applications, seed)
    interviews = generate_interviews(applications, assessments, seed)
    offers = generate_offers(applications, interviews, seed)
    hires = generate_hires(offers, seed)
    planted = plant_violations(applications, assessments, interviews, offers, hires)
    return {
        "requisitions": requisitions,
        "candidates": candidates,
        "applications": planted["applications"],
        "assessments": planted["assessments"],
        "interviews": planted["interviews"],
        "offers": planted["offers"],
        "hires": planted["hires"],
    }


def check_interview_after_application(
    interviews: pd.DataFrame, applications: pd.DataFrame
) -> CheckResult:
    """Fail if any interview is dated before its application date."""
    applied_by_app = applications.set_index("application_id")["applied_date"]
    failing: list[int] = []
    for idx, row in interviews.iterrows():
        if row["application_id"] not in applied_by_app.index:
            continue  # referential checks own those rows
        if row["interview_date"] < applied_by_app.loc[row["application_id"]]:
            failing.append(int(idx))
    if not failing:
        return CheckResult(
            "interview_after_application", True, "all interviews on or after application"
        )
    return CheckResult(
        "interview_after_application",
        False,
        f"{len(failing)} interviews dated before application",
        failing,
    )


def check_hire_has_offer(hires: pd.DataFrame, offers: pd.DataFrame) -> CheckResult:
    """Fail if any hire traces to an offer_id that does not exist."""
    return check_referential_integrity(hires, "offer_id", offers, "offer_id")


def validate_applications(
    applications: pd.DataFrame,
    requisitions: pd.DataFrame,
    candidates: pd.DataFrame,
) -> list[CheckResult]:
    """All application checks: completeness, uniqueness, refs."""
    return [
        check_completeness(
            applications, ["application_id", "req_id", "candidate_id", "applied_date"]
        ),
        check_uniqueness(applications, "application_id"),
        check_referential_integrity(applications, "req_id", requisitions, "req_id"),
        check_referential_integrity(
            applications, "candidate_id", candidates, "candidate_id"
        ),
    ]


def validate_assessments(
    assessments: pd.DataFrame, applications: pd.DataFrame
) -> list[CheckResult]:
    """All assessment checks: completeness, uniqueness, score range, refs."""
    return [
        check_completeness(
            assessments, ["assessment_id", "application_id", "score"]
        ),
        check_uniqueness(assessments, "assessment_id"),
        check_ranges(assessments, "score", 0, 100),
        check_referential_integrity(
            assessments, "application_id", applications, "application_id"
        ),
    ]


def validate_interviews(
    interviews: pd.DataFrame, applications: pd.DataFrame
) -> list[CheckResult]:
    """All interview checks: completeness, uniqueness, date rule, refs."""
    return [
        check_completeness(
            interviews, ["interview_id", "application_id", "interview_date"]
        ),
        check_uniqueness(interviews, "interview_id"),
        check_referential_integrity(
            interviews, "application_id", applications, "application_id"
        ),
        check_interview_after_application(interviews, applications),
    ]


def validate_offers(
    offers: pd.DataFrame,
    applications: pd.DataFrame,
    requisitions: pd.DataFrame,
) -> list[CheckResult]:
    """All offer checks: completeness, uniqueness, refs."""
    return [
        check_completeness(
            offers, ["offer_id", "application_id", "req_id", "offer_date"]
        ),
        check_uniqueness(offers, "offer_id"),
        check_referential_integrity(
            offers, "application_id", applications, "application_id"
        ),
        check_referential_integrity(offers, "req_id", requisitions, "req_id"),
    ]


def validate_hires(
    hires: pd.DataFrame, offers: pd.DataFrame, applications: pd.DataFrame
) -> list[CheckResult]:
    """All hire checks: completeness, uniqueness, offer trace, refs."""
    return [
        check_completeness(hires, ["hire_id", "offer_id", "application_id"]),
        check_uniqueness(hires, "hire_id"),
        check_hire_has_offer(hires, offers),
        check_referential_integrity(
            hires, "application_id", applications, "application_id"
        ),
    ]


def _quarantine(df: pd.DataFrame, checks: list[CheckResult], key: str):
    """Split a table into silver (clean) and quarantine (failed, with reason)."""
    reasons: dict[int, list[str]] = {}
    for result in checks:
        for row in result.failing_rows:
            reasons.setdefault(row, []).append(result.name)
    mask = pd.Series(False, index=df.index)
    for row in reasons:
        mask.loc[row] = True
    quarantine = df.loc[mask].copy()
    quarantine["quarantine_reason"] = [
        "; ".join(reasons[i]) for i in quarantine.index
    ]
    silver = df.loc[~mask].copy()
    silver = silver.drop_duplicates(subset=[key], keep="first")
    return silver.reset_index(drop=True), quarantine.reset_index(drop=True)


def quarantine_applications(
    applications: pd.DataFrame,
    requisitions: pd.DataFrame,
    candidates: pd.DataFrame,
):
    return _quarantine(
        applications, validate_applications(applications, requisitions, candidates),
        "application_id",
    )


def quarantine_assessments(assessments: pd.DataFrame, applications: pd.DataFrame):
    return _quarantine(
        assessments, validate_assessments(assessments, applications), "assessment_id"
    )


def quarantine_interviews(interviews: pd.DataFrame, applications: pd.DataFrame):
    return _quarantine(
        interviews, validate_interviews(interviews, applications), "interview_id"
    )


def quarantine_offers(
    offers: pd.DataFrame,
    applications: pd.DataFrame,
    requisitions: pd.DataFrame,
):
    return _quarantine(
        offers, validate_offers(offers, applications, requisitions), "offer_id"
    )


def quarantine_hires(
    hires: pd.DataFrame, offers: pd.DataFrame, applications: pd.DataFrame
):
    return _quarantine(
        hires, validate_hires(hires, offers, applications), "hire_id"
    )


def build_funnel_model(
    silver_applications: pd.DataFrame,
    requisitions: pd.DataFrame,
    silver_assessments: pd.DataFrame,
    silver_interviews: pd.DataFrame,
    silver_offers: pd.DataFrame,
    silver_hires: pd.DataFrame,
) -> pd.DataFrame:
    """Candidate-funnel model: one row per clean application.

    Joins the application to its requisition and department, then
    marks the furthest stage reached (assessed, interviewed, offered,
    hired) from the silver stage tables, with assessment score,
    interview count, and days from application to hire. Applications
    whose stage rows were quarantined stay at the earlier stage —
    a bad assessment never promotes an application.
    """
    app = silver_applications.merge(
        requisitions[["req_id", "title", "department", "location"]],
        on="req_id",
        how="left",
    )
    assessed = silver_assessments.set_index("application_id")
    app["assessed"] = app["application_id"].isin(set(assessed.index))
    app["assessment_score"] = app["application_id"].map(
        assessed["score"] if len(assessed) else pd.Series(dtype="float64")
    )
    interview_counts = silver_interviews.groupby("application_id").size()
    app["interview_count"] = (
        app["application_id"].map(interview_counts).fillna(0).astype("int64")
    )
    app["interviewed"] = app["interview_count"] > 0
    offered = silver_offers.set_index("application_id")
    app["offered"] = app["application_id"].isin(set(offered.index))
    hired = silver_hires.set_index("application_id")
    app["hired"] = app["application_id"].isin(set(hired.index))
    hire_dates = silver_hires.set_index("application_id")["start_date"]
    app["hire_date"] = app["application_id"].map(hire_dates)
    app["days_to_hire"] = (
        (app["hire_date"] - app["applied_date"]).dt.days
    )
    app["stage"] = "Applied"
    app.loc[app["assessed"], "stage"] = "Assessed"
    app.loc[app["interviewed"], "stage"] = "Interviewed"
    app.loc[app["offered"], "stage"] = "Offered"
    app.loc[app["hired"], "stage"] = "Hired"
    return app.sort_values("application_id").reset_index(drop=True)


def build_funnel_view(funnel: pd.DataFrame) -> pd.DataFrame:
    """Gold funnel view: one row per department with stage conversion rates."""
    view = (
        funnel.groupby("department", as_index=False)
        .agg(
            applications=("application_id", "count"),
            assessed=("assessed", "sum"),
            interviewed=("interviewed", "sum"),
            offered=("offered", "sum"),
            hired=("hired", "sum"),
        )
    )
    view["assessment_rate"] = (view["assessed"] / view["applications"]).round(2)
    view["interview_rate"] = (
        (view["interviewed"] / view["assessed"]).replace(
            [np.inf, -np.inf], np.nan
        ).fillna(0).round(2)
    )
    view["offer_rate"] = (
        (view["offered"] / view["interviewed"]).replace(
            [np.inf, -np.inf], np.nan
        ).fillna(0).round(2)
    )
    view["hire_rate"] = (
        (view["hired"] / view["offered"]).replace(
            [np.inf, -np.inf], np.nan
        ).fillna(0).round(2)
    )
    view["overall_hire_rate"] = (view["hired"] / view["applications"]).round(2)
    return view.sort_values("department").reset_index(drop=True)


def build_requisition_view(
    funnel: pd.DataFrame, requisitions: pd.DataFrame
) -> pd.DataFrame:
    """Gold requisition view: one row per requisition.

    Applications, hires, fill rate against headcount, and median days
    to hire — the numbers a hiring team reads to see which reqs are
    moving and which are stuck.
    """
    agg = (
        funnel.groupby("req_id", as_index=False)
        .agg(
            applications=("application_id", "count"),
            hires=("hired", "sum"),
            median_days_to_hire=("days_to_hire", "median"),
        )
    )
    view = requisitions.merge(agg, on="req_id", how="left")
    view["applications"] = view["applications"].fillna(0).astype("int64")
    view["hires"] = view["hires"].fillna(0).astype("int64")
    view["fill_rate"] = (view["hires"] / view["headcount"]).round(2)
    return view.sort_values("req_id").reset_index(drop=True)


def check_funnel_reconciliation(
    funnel: pd.DataFrame,
    silver_assessments: pd.DataFrame,
    silver_interviews: pd.DataFrame,
    silver_offers: pd.DataFrame,
    silver_hires: pd.DataFrame,
    funnel_view: pd.DataFrame,
    requisition_view: pd.DataFrame,
) -> CheckResult:
    """Fail if the vended views disagree with the funnel model or silver.

    Stage rows whose application was quarantined are not vendable: they
    cannot be counted under an application the funnel does not hold,
    so the check compares against vendable stage rows only.
    """
    funnel_apps = set(funnel["application_id"])
    vendable_asm = silver_assessments[
        silver_assessments["application_id"].isin(funnel_apps)
    ]
    vendable_int = silver_interviews[
        silver_interviews["application_id"].isin(funnel_apps)
    ]
    vendable_ofr = silver_offers[
        silver_offers["application_id"].isin(funnel_apps)
    ]
    vendable_hir = silver_hires[
        silver_hires["application_id"].isin(funnel_apps)
    ]
    problems = []
    if int(funnel["assessed"].sum()) != len(vendable_asm):
        problems.append("funnel assessed count does not match silver assessments")
    if int(funnel["interview_count"].sum()) != len(vendable_int):
        problems.append("funnel interview count does not match silver interviews")
    if int(funnel["offered"].sum()) != len(vendable_ofr):
        problems.append("funnel offered count does not match silver offers")
    if int(funnel["hired"].sum()) != len(vendable_hir):
        problems.append("funnel hired count does not match silver hires")
    if int(funnel_view["applications"].sum()) != len(funnel):
        problems.append("funnel view applications do not sum to funnel rows")
    if int(requisition_view["applications"].sum()) != len(funnel):
        problems.append("requisition view applications do not sum to funnel rows")
    if problems:
        return CheckResult("funnel_reconciliation", False, "; ".join(problems))
    return CheckResult(
        "funnel_reconciliation",
        True,
        f"views reconcile: {len(funnel)} applications, "
        f"{int(funnel['hired'].sum())} hires",
    )


def generate_recruiting_events(n: int = 150, seed: int = 42) -> pd.DataFrame:
    """Synthetic candidate-funnel event stream with planted late events and duplicates.

    150 events: 3 are duplicate deliveries of earlier event ids, 2
    arrive with an event time older than the watermark will allow
    (late data). Each event names its funnel stage and the application
    it concerns, the way a service log event would.
    """
    from datetime import datetime, timedelta, timezone

    rng = _rng(seed + 7)
    base = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)
    event_times = [base + timedelta(minutes=int(m)) for m in rng.integers(0, 600, size=n)]
    event_times.sort()
    df = pd.DataFrame(
        {
            "offset": list(range(n)),
            "event_id": [f"E{i:05d}" for i in range(n)],
            "event_time": pd.to_datetime(event_times, utc=True),
            "ingested_at": pd.to_datetime(
                [t + timedelta(seconds=int(s)) for t, s in zip(event_times, rng.integers(5, 120, size=n))],
                utc=True,
            ),
            "stage": rng.choice(
                ["applied", "assessed", "interviewed", "offered", "hired"], size=n
            ),
            "application_id": [f"APP-{30001 + int(i)}" for i in rng.integers(0, 300, size=n)],
            "event_type": rng.choice(["created", "updated", "completed"], size=n),
        }
    )
    dupes = df.iloc[[5, 40, 90]].copy()
    dupes["offset"] = [n, n + 1, n + 2]
    late = df.iloc[[10, 60]].copy()
    late["event_id"] = ["E90001", "E90002"]
    late["offset"] = [n + 3, n + 4]
    late["event_time"] = pd.to_datetime(
        [base - timedelta(hours=3), base - timedelta(hours=2, minutes=30)], utc=True
    )
    stream = pd.concat([df, dupes, late], ignore_index=True)
    return stream.sort_values("offset").reset_index(drop=True)


def run_recruiting_stream(events: pd.DataFrame) -> dict:
    """Process the recruiting event stream exactly once via the shared streamer."""
    return run_stream(events)


def load_assessment_batch(
    assessments: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Nightly batch load: dedup on assessment_id, keep first; return (loaded, duplicates)."""
    dup_mask = assessments.duplicated(subset=["assessment_id"], keep="first")
    duplicates = assessments.loc[dup_mask].copy().reset_index(drop=True)
    loaded = assessments.loc[~dup_mask].copy().reset_index(drop=True)
    return loaded, duplicates
