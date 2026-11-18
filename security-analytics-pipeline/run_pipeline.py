"""Run the full security-analytics pipeline and write the report.

Usage: python run_pipeline.py [--out DIR]
Writes the SQLite database to <out>/security_analytics.db, lineage to
lineage.json, the evidence report to evidence_report.json, and a
human-readable validation_report.txt in the project root.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from security_analytics import (
    build_evidence,
    connect,
    create_tables,
    evidence_completeness,
    find_all_anomalies,
    generate_all,
    load_dimensions,
    load_raw,
    normalize,
    compute_kpis,
    render_report,
    run_all_checks,
    table_counts,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="security_tables")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)

    data = generate_all()

    db_path = out / "security_analytics.db"
    if db_path.exists():
        db_path.unlink()
    conn = connect(db_path)
    create_tables(conn)

    raw_counts = load_raw(conn, data)
    print(f"staged login events: {raw_counts['raw_login_events']}")
    print(f"staged audit events: {raw_counts['raw_audit_events']}")
    print(f"staged findings: {raw_counts['raw_findings']}")

    dim_counts = load_dimensions(conn, data)
    print(f"identities: {dim_counts['identities']}, assets: {dim_counts['assets']}")

    # Data-quality checks run on the staged raw data.
    checks = run_all_checks(data)
    passed = sum(1 for c in checks if c.passed)
    print(f"data-quality checks: {passed} of {len(checks)} passed")

    # Normalize; bad rows go to quarantine, late rows are flagged.
    result = normalize(conn, data)
    print(f"normalized events: {result['events']}")
    print(f"normalized findings: {result['findings']}")
    print(f"quarantined rows: {result['quarantine']}")

    counts = table_counts(conn)
    counts.update(result)
    kpis = compute_kpis(conn)
    anomalies = find_all_anomalies(conn)
    evidence = build_evidence(kpis, anomalies, checks)
    evidence_pct = evidence_completeness(evidence)

    report = render_report(
        checks=checks,
        counts=counts,
        kpis=kpis,
        anomalies=anomalies,
        evidence=evidence,
        evidence_pct=evidence_pct,
    )
    (root / "validation_report.txt").write_text(report)
    (root / "lineage.json").write_text(
        json.dumps({"lineage": result["lineage"]}, indent=2, sort_keys=True)
    )
    (root / "evidence_report.json").write_text(
        json.dumps(
            {
                "kpis": kpis,
                "anomalies": anomalies,
                "evidence": evidence,
                "evidence_completeness_pct": evidence_pct,
            },
            indent=2,
            default=str,
        )
    )
    print()
    print(report)
    conn.close()


if __name__ == "__main__":
    main()
