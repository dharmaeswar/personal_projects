"""Reporting: Power BI-style dashboard rows, exception queue, sign-off
checklist, and the text/CSV risk report.
"""

from __future__ import annotations

import csv
from pathlib import Path


class ExceptionQueue:
    """Most-severe-first queue: breaches and failed controls are reviewed,
    never dropped or silently included."""

    SEVERITY = {"BREACH": 0, "High residual": 1, "Ineffective control": 2, "WARNING": 3}

    def __init__(self):
        self.items = []

    def add(self, severity, kind, ref, detail):
        if severity not in self.SEVERITY:
            raise ValueError(f"unknown severity {severity!r}")
        self.items.append({"severity": severity, "kind": kind, "ref": ref, "detail": detail})

    def ordered(self):
        return sorted(self.items, key=lambda i: self.SEVERITY[i["severity"]])


def dashboard_rows(rcsa_rows, kri_rows):
    """One row per risk + KRI, shaped for a Power BI dashboard import."""
    rows = []
    for r in rcsa_rows:
        rows.append({
            "type": "RCSA risk", "id": r["risk_id"], "name": r["name"],
            "category": r["category"], "source": r["source"],
            "value": r["residual"], "status": r["residual_band"],
        })
    for k in kri_rows:
        rows.append({
            "type": "KRI", "id": k["kri_id"], "name": k["name"],
            "category": "-", "source": "-",
            "value": k["current"], "status": k["status"],
        })
    return rows


def write_csv(path, rows, columns):
    path = Path(path)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in columns})


def render_report(as_of, rcsa_rows, kri_rows, framework, recon, top_event, queue):
    high = [r for r in rcsa_rows if r["residual_band"] == "High"]
    breached = [k for k in kri_rows if k["status"] == "BREACH"]
    lines = [
        "ENTERPRISE RISK MANAGEMENT — TECHNOLOGY RISK REPORT",
        f"As of {as_of} | Sources: IT, IS, Third Party, Data Management",
        "",
        f"RCSA: {len(rcsa_rows)} risks assessed; {len(high)} High residual risk.",
        f"KRIs: {len(kri_rows)} tracked; {len(breached)} in BREACH: "
        + (", ".join(k['kri_id'] for k in breached) or "none"),
        f"Framework coverage: {framework['overall_coverage']}% "
        f"({len(framework['gaps'])} open gaps).",
        f"Loss reconciliation Python vs SQL: {'PASS' if recon['ok'] else 'FAIL'}.",
        f"Largest loss event: {top_event['event_id']} "
        f"({top_event['category']}/{top_event['source']}) ${top_event['amount']:,.2f}.",
        "",
        "HIGH RESIDUAL RISKS",
    ]
    for r in high:
        lines.append(f"- {r['risk_id']} {r['name']} — residual {r['residual']} ({r['residual_band']}). {r['challenge']}")
    lines += ["", "BREACHED / EMERGING KRIs"]
    for k in kri_rows:
        if k["status"] == "BREACH" or k["emerging_risk"]:
            lines.append(f"- {k['kri_id']} {k['name']}: {k['current']} {k['unit']} — {k['status']}"
                         + ("; EMERGING RISK (worsening trend)" if k["emerging_risk"] else ""))
    lines += ["", "OPEN EXCEPTIONS (most severe first)"]
    for item in queue.ordered():
        lines.append(f"- [{item['severity']}] {item['kind']} {item['ref']}: {item['detail']}")
    return "\n".join(lines) + "\n"


def signoff_checklist():
    """Five control steps that must be signed before the report goes out."""
    return [
        {"step": 1, "check": "RCSA scores reviewed with 1LOD owners", "signed": False},
        {"step": 2, "check": "Breached KRIs explained to senior management", "signed": False},
        {"step": 3, "check": "Exceptions cleared or escalated", "signed": False},
        {"step": 4, "check": "Python vs SQL figures reconciled", "signed": False},
        {"step": 5, "check": "Report distributed to risk committee", "signed": False},
    ]
