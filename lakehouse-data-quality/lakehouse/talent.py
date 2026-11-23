"""Talent data foundations: streaming + batch ingestion into a unified talent model.

An Amazon Talent Solutions (ITDS) Data Foundations team unifies talent
service domains — employees, roles, skills, learning records — into one
cross-cutting talent data model, vended for analytics and operational use.
This module models that flow with synthetic, seeded data (no real
employee or company data anywhere):

- **Streaming ingest** — talent change events (employee, role, skill,
  learning updates) arrive as micro-batches and are processed exactly
  once by reusing :func:`lakehouse.streaming.run_stream`: dedup on
  ``event_id`` against a checkpoint, late events dropped at the
  watermark. In production this is Kinesis / FireHose into Redshift;
  here it runs locally with pandas, and the code says so.
- **Batch ingest** — a nightly learning-records batch, deduplicated on
  ``record_id`` (keep first), the way a Glue ETL job would load it.
- **Unified talent model** — one row per employee: current role and
  department, skill list, learning count, last learning date, average
  learning score. Built only from clean (silver) rows.
- **Vended views** — an analytics view (per-department headcount,
  average skills, learning coverage) and an operational view (one row
  per employee: current role, skills, latest learning) for downstream
  integrations.
- **Quality checks** — completeness, uniqueness, referential integrity,
  score ranges, and two talent rules: every learning record must fall
  on or after the employee's hire date, and every employee's role must
  exist. Bad rows are quarantined with a reason, never dropped silently.
- **Query tuning** — an inefficient per-employee scan loop versus a
  single grouped aggregation, with measured wall times.

The fixture plants 8 bad rows on purpose so the checks have real
violations to catch:

- 2 duplicate learning ``record_id`` values
- 2 null ``employee_id`` values in learning records
- 1 learning record for an unknown employee (EMP-9999)
- 1 learning record completed before the employee's hire date
- 1 learning record for an unknown skill (S-999)
- 1 employee whose ``role_id`` does not exist (R-999)
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

DEPARTMENTS = ["Engineering", "Data", "People Ops", "Finance", "Product"]

ROLE_TITLES = [
    "Software Engineer",
    "Data Engineer",
    "Data Scientist",
    "Recruiter",
    "HR Business Partner",
    "Financial Analyst",
    "Product Manager",
    "Engineering Manager",
    "Analytics Engineer",
    "Learning Designer",
    "Compensation Analyst",
    "Program Manager",
    "ML Engineer",
    "Business Analyst",
    "Talent Coordinator",
    "Data Analyst",
    "Solutions Architect",
    "People Analytics Lead",
    "Operations Analyst",
    "UX Researcher",
]

SKILL_NAMES = [
    ("Python", "programming"),
    ("SQL", "data"),
    ("Spark", "data"),
    ("AWS", "cloud"),
    ("Kafka", "data"),
    ("Statistics", "analytics"),
    ("Machine Learning", "analytics"),
    ("Data Modeling", "data"),
    ("ETL Pipelines", "data"),
    ("Communication", "leadership"),
    ("Mentoring", "leadership"),
    ("Project Management", "leadership"),
    ("Excel", "analytics"),
    ("Tableau", "analytics"),
    ("Redshift", "cloud"),
    ("Docker", "cloud"),
    ("Kubernetes", "cloud"),
    ("Java", "programming"),
    ("JavaScript", "programming"),
    ("R", "analytics"),
    ("SAS", "analytics"),
    ("Databricks", "data"),
    ("Snowflake", "data"),
    ("Airflow", "data"),
    ("Git", "programming"),
    ("Linux", "cloud"),
    ("Testing", "programming"),
    ("Validation", "analytics"),
    ("Negotiation", "leadership"),
    ("Stakeholder Management", "leadership"),
]

COURSES = [
    "Data Foundations 101",
    "Advanced SQL",
    "Streaming Systems",
    "Leadership Essentials",
    "Cloud Practitioner",
    "Analytics With Python",
]

N_EMPLOYEES = 60
N_LEARNING_BASE = 180


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def generate_roles(seed: int = 42) -> pd.DataFrame:
    """20 roles, each in one of 5 departments."""
    rng = _rng(seed)
    return pd.DataFrame(
        {
            "role_id": [f"R-{i + 1:02d}" for i in range(20)],
            "role_title": ROLE_TITLES,
            "department": rng.choice(DEPARTMENTS, size=20),
        }
    )


def generate_skills() -> pd.DataFrame:
    """30 skills with a category each."""
    return pd.DataFrame(
        {
            "skill_id": [f"S-{i + 1:02d}" for i in range(30)],
            "skill_name": [name for name, _ in SKILL_NAMES],
            "category": [cat for _, cat in SKILL_NAMES],
        }
    )


def generate_employees(roles: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """60 synthetic employees, each on a role, hired 2023-01 to 2026-06."""
    rng = _rng(seed)
    hires = pd.to_datetime(
        rng.integers(
            pd.Timestamp("2023-01-01").value,
            pd.Timestamp("2026-06-30").value,
            size=N_EMPLOYEES,
        )
    )
    return pd.DataFrame(
        {
            "employee_id": [f"EMP-{1001 + i}" for i in range(N_EMPLOYEES)],
            "full_name": [f"Employee {1001 + i}" for i in range(N_EMPLOYEES)],
            "role_id": rng.choice(roles["role_id"].tolist(), size=N_EMPLOYEES),
            "hire_date": hires,
            "location": rng.choice(["Seattle", "Remote", "Arlington"], size=N_EMPLOYEES),
        }
    )


def generate_employee_skills(
    employees: pd.DataFrame, skills: pd.DataFrame, seed: int = 42
) -> pd.DataFrame:
    """Bridge rows: each employee holds 2-5 skills."""
    rng = _rng(seed + 2)
    rows = []
    for emp in employees["employee_id"]:
        n = int(rng.integers(2, 6))
        chosen = rng.choice(skills["skill_id"].tolist(), size=n, replace=False)
        for skill_id in chosen:
            rows.append({"employee_id": emp, "skill_id": skill_id})
    return pd.DataFrame(rows)


def generate_learning(
    employees: pd.DataFrame, skills: pd.DataFrame, seed: int = 42
) -> pd.DataFrame:
    """180 synthetic learning records, each completed after the hire date."""
    rng = _rng(seed + 3)
    hire_by_emp = employees.set_index("employee_id")["hire_date"]
    rows = []
    for i in range(N_LEARNING_BASE):
        emp = str(rng.choice(employees["employee_id"].tolist()))
        hire = hire_by_emp.loc[emp]
        max_days = max((pd.Timestamp("2026-11-01") - hire).days, 1)
        rows.append(
            {
                "record_id": f"LR-{20001 + i}",
                "employee_id": emp,
                "skill_id": str(rng.choice(skills["skill_id"].tolist())),
                "course": str(rng.choice(COURSES)),
                "completion_date": hire + pd.Timedelta(days=int(rng.integers(0, max_days))),
                "score": int(rng.integers(60, 101)),
            }
        )
    return pd.DataFrame(rows)


def plant_violations(
    learning: pd.DataFrame, employees: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Plant 8 bad rows: 7 bad learning rows and 1 bad employee. Returns copies."""
    learning = learning.copy()
    employees = employees.copy()
    # 2 duplicate learning record_ids (copies of rows 0 and 1).
    dup = learning.iloc[[0, 1]].copy()
    learning = pd.concat([learning, dup], ignore_index=True)
    # 2 null employee_ids.
    learning.loc[learning.index[2], "employee_id"] = None
    learning.loc[learning.index[3], "employee_id"] = None
    # 1 learning record for an unknown employee.
    learning.loc[learning.index[4], "employee_id"] = "EMP-9999"
    # 1 learning record completed before the employee's hire date.
    row = learning.iloc[5]
    hire = employees.loc[
        employees["employee_id"] == row["employee_id"], "hire_date"
    ].iloc[0]
    learning.loc[learning.index[5], "completion_date"] = hire - pd.Timedelta(days=30)
    # 1 learning record for an unknown skill.
    learning.loc[learning.index[6], "skill_id"] = "S-999"
    # 1 employee whose role does not exist.
    employees.loc[employees.index[0], "role_id"] = "R-999"
    return learning, employees


def generate_talent(seed: int = 42) -> dict[str, pd.DataFrame]:
    """Seeded talent domains with the 8 planted violations."""
    roles = generate_roles(seed)
    skills = generate_skills()
    employees = generate_employees(roles, seed)
    emp_skills = generate_employee_skills(employees, skills, seed)
    learning = generate_learning(employees, skills, seed)
    learning, employees = plant_violations(learning, employees)
    return {
        "roles": roles,
        "skills": skills,
        "employees": employees,
        "employee_skills": emp_skills,
        "learning": learning,
    }


def check_learning_after_hire(
    learning: pd.DataFrame, employees: pd.DataFrame
) -> CheckResult:
    """Fail if any learning completion predates the employee's hire date."""
    hire_by_emp = employees.set_index("employee_id")["hire_date"]
    failing: list[int] = []
    for idx, row in learning.iterrows():
        if pd.isna(row["employee_id"]) or row["employee_id"] not in hire_by_emp.index:
            continue  # completeness / referential checks own those rows
        if row["completion_date"] < hire_by_emp.loc[row["employee_id"]]:
            failing.append(int(idx))
    if not failing:
        return CheckResult(
            "learning_after_hire", True, "all learning completed on or after hire"
        )
    return CheckResult(
        "learning_after_hire",
        False,
        f"{len(failing)} learning records completed before hire",
        failing,
    )


def validate_learning(
    learning: pd.DataFrame, employees: pd.DataFrame, skills: pd.DataFrame
) -> list[CheckResult]:
    """All learning checks: completeness, uniqueness, ranges, refs, hire rule."""
    return [
        check_completeness(learning, ["record_id", "employee_id", "completion_date"]),
        check_uniqueness(learning, "record_id"),
        check_ranges(learning, "score", 0, 100),
        check_referential_integrity(learning, "employee_id", employees, "employee_id"),
        check_referential_integrity(learning, "skill_id", skills, "skill_id"),
        check_learning_after_hire(learning, employees),
    ]


def validate_employees(
    employees: pd.DataFrame, roles: pd.DataFrame
) -> list[CheckResult]:
    """Completeness, uniqueness and role-reference checks for employees."""
    return [
        check_completeness(employees, ["employee_id", "role_id", "hire_date"]),
        check_uniqueness(employees, "employee_id"),
        check_referential_integrity(employees, "role_id", roles, "role_id"),
    ]


def quarantine_learning(
    learning: pd.DataFrame, employees: pd.DataFrame, skills: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split learning into silver (clean) and quarantine (failed, with reason).

    A record fails if it trips any learning check. Duplicate record_ids
    keep only the first occurrence in silver.
    """
    checks = validate_learning(learning, employees, skills)
    reasons: dict[int, list[str]] = {}
    for result in checks:
        for row in result.failing_rows:
            reasons.setdefault(row, []).append(result.name)
    mask = pd.Series(False, index=learning.index)
    for row in reasons:
        mask.loc[row] = True
    quarantine = learning.loc[mask].copy()
    quarantine["quarantine_reason"] = [
        "; ".join(reasons[i]) for i in quarantine.index
    ]
    silver = learning.loc[~mask].copy()
    silver = silver.drop_duplicates(subset=["record_id"], keep="first")
    return silver.reset_index(drop=True), quarantine.reset_index(drop=True)


def quarantine_employees(
    employees: pd.DataFrame, roles: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split employees into silver (clean) and quarantine (failed, with reason)."""
    checks = validate_employees(employees, roles)
    reasons: dict[int, list[str]] = {}
    for result in checks:
        for row in result.failing_rows:
            reasons.setdefault(row, []).append(result.name)
    mask = pd.Series(False, index=employees.index)
    for row in reasons:
        mask.loc[row] = True
    quarantine = employees.loc[mask].copy()
    quarantine["quarantine_reason"] = [
        "; ".join(reasons[i]) for i in quarantine.index
    ]
    silver = employees.loc[~mask].copy()
    silver = silver.drop_duplicates(subset=["employee_id"], keep="first")
    return silver.reset_index(drop=True), quarantine.reset_index(drop=True)


def build_unified_model(
    silver_employees: pd.DataFrame,
    roles: pd.DataFrame,
    employee_skills: pd.DataFrame,
    skills: pd.DataFrame,
    silver_learning: pd.DataFrame,
) -> pd.DataFrame:
    """Cross-cutting talent model: one row per clean employee.

    Joins the employee to its role and department, aggregates its skills
    into a list, and aggregates its learning into a count, last date and
    average score. Employees with no learning get count 0 and nulls.
    Learning rows that belong to a quarantined employee are held back:
    they cannot be vended under an employee who failed validation.
    """
    silver_learning = silver_learning[
        silver_learning["employee_id"].isin(set(silver_employees["employee_id"]))
    ]
    emp = silver_employees.merge(
        roles[["role_id", "role_title", "department"]], on="role_id", how="left"
    )
    skill_names = skills.set_index("skill_id")["skill_name"]
    skill_lists = (
        employee_skills.groupby("employee_id")["skill_id"]
        .apply(lambda ids: sorted(skill_names.loc[i] for i in ids))
        .rename("skills")
    )
    learn_agg = (
        silver_learning.groupby("employee_id", as_index=False)
        .agg(
            learning_count=("record_id", "count"),
            last_learning_date=("completion_date", "max"),
            avg_score=("score", "mean"),
        )
    )
    unified = emp.merge(skill_lists, on="employee_id", how="left")
    unified = unified.merge(learn_agg, on="employee_id", how="left")
    unified["skills"] = unified["skills"].apply(
        lambda v: v if isinstance(v, list) else []
    )
    unified["skill_count"] = unified["skills"].apply(len)
    unified["learning_count"] = unified["learning_count"].fillna(0).astype("int64")
    unified["avg_score"] = unified["avg_score"].round(1)
    return unified.sort_values("employee_id").reset_index(drop=True)


def build_analytics_view(unified: pd.DataFrame) -> pd.DataFrame:
    """Gold analytics view: one row per department.

    Headcount, average skills per employee, average learning records
    per employee, and share of employees with at least one learning
    record — the numbers an analytics team would chart.
    """
    view = (
        unified.groupby("department", as_index=False)
        .agg(
            headcount=("employee_id", "count"),
            avg_skill_count=("skill_count", "mean"),
            avg_learning_count=("learning_count", "mean"),
            employees_with_learning=("learning_count", lambda s: int((s > 0).sum())),
        )
    )
    view["avg_skill_count"] = view["avg_skill_count"].round(2)
    view["avg_learning_count"] = view["avg_learning_count"].round(2)
    view["learning_coverage"] = (
        view["employees_with_learning"] / view["headcount"]
    ).round(2)
    return view.sort_values("department").reset_index(drop=True)


def build_operational_view(unified: pd.DataFrame) -> pd.DataFrame:
    """Gold operational view: one row per employee, for downstream integrations.

    Current role, department, skill list, latest learning date and
    average score — the fields a downstream service reads to decide
    what a person can do and what they learned most recently.
    """
    return unified[
        [
            "employee_id",
            "full_name",
            "role_title",
            "department",
            "skills",
            "skill_count",
            "learning_count",
            "last_learning_date",
            "avg_score",
        ]
    ].copy()


def check_unified_reconciliation(
    unified: pd.DataFrame,
    silver_learning: pd.DataFrame,
    analytics_view: pd.DataFrame,
) -> CheckResult:
    """Fail if the vended views disagree with the unified model or silver."""
    vendable_learning = silver_learning[
        silver_learning["employee_id"].isin(set(unified["employee_id"]))
    ]
    problems = []
    if int(unified["learning_count"].sum()) != len(vendable_learning):
        problems.append("unified learning counts do not sum to silver learning rows")
    if int(analytics_view["headcount"].sum()) != len(unified):
        problems.append("analytics headcount does not sum to unified employees")
    if int(analytics_view["employees_with_learning"].sum()) != int(
        (unified["learning_count"] > 0).sum()
    ):
        problems.append("analytics learning coverage does not match unified model")
    if problems:
        return CheckResult("talent_reconciliation", False, "; ".join(problems))
    return CheckResult(
        "talent_reconciliation",
        True,
        f"views reconcile: {len(unified)} employees, "
        f"{len(vendable_learning)} vendable learning records",
    )


def generate_talent_events(n: int = 120, seed: int = 42) -> pd.DataFrame:
    """Synthetic talent change-event stream with planted late events and duplicates.

    120 events: 3 are duplicate deliveries of earlier event ids, 2 arrive
    with an event time older than the watermark will allow (late data).
    Each event names its domain (employee / role / skill / learning) and
    the employee it concerns, the way a service log event would.
    """
    from datetime import datetime, timedelta, timezone

    rng = _rng(seed + 5)
    base = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)
    event_times = [base + timedelta(minutes=int(m)) for m in rng.integers(0, 600, size=n)]
    event_times.sort()
    df = pd.DataFrame(
        {
            "offset": list(range(n)),
            "event_id": [f"T{i:05d}" for i in range(n)],
            "event_time": pd.to_datetime(event_times, utc=True),
            "ingested_at": pd.to_datetime(
                [t + timedelta(seconds=int(s)) for t, s in zip(event_times, rng.integers(5, 120, size=n))],
                utc=True,
            ),
            "domain": rng.choice(["employee", "role", "skill", "learning"], size=n),
            "employee_id": [f"EMP-{1001 + int(i)}" for i in rng.integers(0, 60, size=n)],
            "event_type": rng.choice(["created", "updated", "completed"], size=n),
        }
    )
    dupes = df.iloc[[5, 40, 90]].copy()
    dupes["offset"] = [n, n + 1, n + 2]
    late = df.iloc[[10, 60]].copy()
    late["event_id"] = ["T90001", "T90002"]
    late["offset"] = [n + 3, n + 4]
    late["event_time"] = pd.to_datetime(
        [base - timedelta(hours=3), base - timedelta(hours=2, minutes=30)], utc=True
    )
    stream = pd.concat([df, dupes, late], ignore_index=True)
    return stream.sort_values("offset").reset_index(drop=True)


def run_talent_stream(events: pd.DataFrame) -> dict:
    """Process the talent event stream exactly once via the shared streamer."""
    return run_stream(events)


def load_learning_batch(learning: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Nightly batch load: dedup on record_id, keep first; return (loaded, duplicates)."""
    dup_mask = learning.duplicated(subset=["record_id"], keep="first")
    duplicates = learning.loc[dup_mask].copy().reset_index(drop=True)
    loaded = learning.loc[~dup_mask].copy().reset_index(drop=True)
    return loaded, duplicates


def tune_query_demo(
    silver_learning: pd.DataFrame, silver_employees: pd.DataFrame
) -> dict:
    """Inefficient query vs tuned query, with measured wall times.

    Slow query (the anti-pattern): for each employee, scan the whole
    learning table to compute that employee's average score — one full
    pass per employee, the way a row-by-row lookup behaves.
    Tuned query: a single group-by aggregation over the same data.
    Both must return identical per-employee averages. The demo tiles
    the learning table to at least 50k rows so the difference is
    measurable; the tiling only repeats seeded rows with new record
    ids, so the averages are unchanged.
    """
    import math

    reps = max(1, math.ceil(50000 / max(len(silver_learning), 1)))
    big = pd.concat([silver_learning] * reps, ignore_index=True)
    big["record_id"] = [f"LR-{90000 + i}" for i in range(len(big))]
    emp_ids = silver_employees["employee_id"].tolist()

    start = time.perf_counter()
    slow = {}
    for emp in emp_ids:
        subset = big[big["employee_id"] == emp]
        slow[emp] = round(float(subset["score"].mean()), 4) if len(subset) else None
    slow_ms = (time.perf_counter() - start) * 1000

    start = time.perf_counter()
    grouped = big.groupby("employee_id")["score"].mean().round(4)
    fast_ms = (time.perf_counter() - start) * 1000
    fast = {emp: (None if emp not in grouped.index else float(grouped.loc[emp])) for emp in emp_ids}

    matches = all(
        (slow[e] is None and fast[e] is None)
        or (slow[e] is not None and fast[e] is not None and abs(slow[e] - fast[e]) < 0.001)
        for e in emp_ids
    )
    return {
        "rows": len(big),
        "employees": len(emp_ids),
        "slow_ms": round(slow_ms, 1),
        "fast_ms": round(fast_ms, 1),
        "speedup": round(slow_ms / fast_ms, 1) if fast_ms > 0 else float("inf"),
        "results_match": matches,
    }
