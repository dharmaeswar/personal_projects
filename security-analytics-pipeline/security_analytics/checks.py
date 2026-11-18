"""Data-quality checks over the staged raw security telemetry.

Each check returns a CheckResult: name, pass/fail, a human-readable
detail string, and the offending row ids. Checks run on the staged raw
tables, so bad source rows are visible before normalization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .data import AS_OF, WATERMARK


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    failing_ids: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"{status} — {self.name}: {self.detail}"


def check_completeness(rows: list[dict], required: list[str], name: str) -> CheckResult:
    failing = [
        str(r.get("event_id") or r.get("finding_id"))
        for r in rows
        if any(r.get(col) is None for col in required)
    ]
    return CheckResult(
        name=name,
        passed=not failing,
        detail=f"{len(failing)} of {len(rows)} rows missing a required field"
        if failing
        else f"all {len(rows)} rows complete",
        failing_ids=failing,
    )


def check_duplicates(rows: list[dict], key: str, name: str) -> CheckResult:
    seen: set[str] = set()
    dupes: list[str] = []
    for r in rows:
        value = str(r[key])
        if value in seen:
            dupes.append(value)
        else:
            seen.add(value)
    return CheckResult(
        name=name,
        passed=not dupes,
        detail=f"{len(dupes)} duplicate {key} value(s)"
        if dupes
        else f"no duplicate {key} values in {len(rows)} rows",
        failing_ids=dupes,
    )


def check_unknown_references(
    rows: list[dict], field: str, valid: set[str], name: str
) -> CheckResult:
    key = "event_id" if "event_id" in rows[0] else "finding_id"
    failing = [
        str(r[key]) for r in rows if r.get(field) is not None and r[field] not in valid
    ]
    return CheckResult(
        name=name,
        passed=not failing,
        detail=f"{len(failing)} row(s) reference an unknown {field}"
        if failing
        else f"all {field} references resolve",
        failing_ids=failing,
    )


def check_late_events(rows: list[dict], name: str) -> CheckResult:
    failing = [
        str(r["event_id"])
        for r in rows
        if r.get("ts") is not None and r["ts"] < WATERMARK
    ]
    return CheckResult(
        name=name,
        passed=not failing,
        detail=f"{len(failing)} event(s) dated before the {WATERMARK.date()} watermark"
        if failing
        else "no events before the watermark",
        failing_ids=failing,
    )


def check_finding_dates(findings: list[dict]) -> CheckResult:
    failing = [
        f["finding_id"]
        for f in findings
        if f["due_date"] < f["discovered_date"]
    ]
    return CheckResult(
        name="finding dates valid (due_date >= discovered_date)",
        passed=not failing,
        detail=f"{len(failing)} finding(s) with due_date before discovered_date"
        if failing
        else f"all {len(findings)} findings have valid dates",
        failing_ids=failing,
    )


def check_finding_discovered_not_future(findings: list[dict]) -> CheckResult:
    failing = [
        f["finding_id"] for f in findings if f["discovered_date"] > AS_OF
    ]
    return CheckResult(
        name="finding discovered_date not in the future",
        passed=not failing,
        detail=f"{len(failing)} finding(s) discovered after {AS_OF.date()}"
        if failing
        else f"all {len(findings)} findings discovered on or before {AS_OF.date()}",
        failing_ids=failing,
    )


def run_all_checks(data: dict) -> list[CheckResult]:
    identities = {i["identity_id"] for i in data["identities"]}
    assets = {a["asset_id"] for a in data["assets"]}
    logins = data["login_events"]
    audits = data["audit_events"]
    findings = data["findings"]
    return [
        check_completeness(logins, ["event_id", "identity_id", "ts"], "login events complete"),
        check_completeness(audits, ["event_id", "identity_id", "asset_id", "ts"], "audit events complete"),
        check_completeness(findings, ["finding_id", "asset_id", "discovered_date", "due_date"], "findings complete"),
        check_duplicates(logins, "event_id", "login event_id unique"),
        check_duplicates(audits, "event_id", "audit event_id unique"),
        check_unknown_references(logins, "identity_id", identities, "login identity references resolve"),
        check_unknown_references(audits, "identity_id", identities, "audit identity references resolve"),
        check_unknown_references(audits, "asset_id", assets, "audit asset references resolve"),
        check_unknown_references(findings, "asset_id", assets, "finding asset references resolve"),
        check_late_events(logins, "login events not late"),
        check_late_events(audits, "audit events not late"),
        check_finding_dates(findings),
        check_finding_discovered_not_future(findings),
    ]
