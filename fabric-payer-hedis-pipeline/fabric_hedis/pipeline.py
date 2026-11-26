"""Monthly payer run: ingest -> validate -> silver -> HEDIS gold ->
vendor round-trip -> health check.

Each step runs once, with one retry on failure, and records its outcome
in ``run_log`` so a failed run can be resumed from the failing step.
Re-running a finished month is idempotent: silver tables are
overwritten, gold rows for the month are replaced, and the vendor file
is rewritten with the same content.
"""

import json
from pathlib import Path

from . import hedis, medallion, monitoring, powerbi, seed
from .sftp_exchange import (FileValidationError, receive_files,
                            send_to_vendor, validate_vendor_return)

INBOUND_FILES = ["members_2026-10.csv", "claims_2026-10.csv",
                 "labs_2026-10.csv", "screenings_2026-10.csv"]
TABLE_FOR_FILE = {
    "members_2026-10.csv": ("bronze_members", seed.MEMBER_COLUMNS),
    "claims_2026-10.csv": ("bronze_claims", seed.CLAIM_COLUMNS),
    "labs_2026-10.csv": ("bronze_labs", seed.LAB_COLUMNS),
    "screenings_2026-10.csv": ("bronze_screenings", seed.SCREENING_COLUMNS),
}


def _run_step(conn, run_id, step, fn):
    """Run one step with a single retry; record outcome in run_log."""
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 - retry once, then record
        try:
            result = fn()
        except Exception as retry_exc:  # noqa: BLE001
            monitoring.record_run(conn, run_id, step, "failed", str(retry_exc))
            raise
        monitoring.record_run(conn, run_id, step, "ok",
                              "succeeded on retry after: %s" % exc)
        return result
    monitoring.record_run(conn, run_id, step, "ok")
    return result


def run_monthly(workdir, month="2026-10", seed_value=42):
    """Execute the full monthly run under ``workdir``. Returns a summary."""
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)
    sftp = work / "sftp"
    inbound = sftp / "inbound"
    outbound = sftp / "outbound"
    db_path = work / "fabric_warehouse.db"
    run_id = "monthly-%s" % month
    conn = medallion.connect(db_path)
    summary = {"month": month, "run_id": run_id}

    def _seed():
        return seed.write_inbound_files(inbound, seed_value)

    summary["manifest"] = _run_step(conn, run_id, "seed_inbound", _seed)

    def _receive():
        return receive_files(inbound)

    received = _run_step(conn, run_id, "sftp_receive_validate", _receive)
    summary["files_received"] = sorted(received)

    def _bronze():
        medallion.clear_bronze(conn)
        counts = {}
        for filename, rows in received.items():
            table, columns = TABLE_FOR_FILE[filename]
            counts[table] = medallion.load_bronze(conn, table, rows, columns)
        return counts

    summary["bronze"] = _run_step(conn, run_id, "load_bronze", _bronze)

    summary["silver"] = _run_step(
        conn, run_id, "promote_silver",
        lambda: medallion.promote_to_silver(conn))
    medallion.save_run_stats(conn, month, summary["silver"])

    def _gold():
        return hedis.compute_hedis(conn, month)

    summary["hedis"] = _run_step(conn, run_id, "compute_hedis", _gold)

    def _vendor():
        rows = [{"measure": r["measure"],
                 "measurement_month": month,
                 "denominator": r["denominator"],
                 "numerator": r["numerator"],
                 "rate": r["rate"]} for r in summary["hedis"]]
        path, entry = send_to_vendor(
            outbound, "hedis_monthly_%s.csv" % month,
            ["measure", "measurement_month", "denominator", "numerator",
             "rate"], rows)
        # The vendor returns an acknowledgement naming every row it
        # accepted; here the round-trip is simulated in-process with all
        # rows accepted, and the ack is validated against the manifest.
        ack = [{"claim_id": r["measure"], "status": "accepted",
                "reason": ""} for r in rows]
        accepted, rejected, problems = validate_vendor_return(
            outbound, "hedis_monthly_%s.csv" % month, ack, [])
        if problems:
            raise FileValidationError("; ".join(problems))
        return {"vendor_file": str(path), "accepted": accepted,
                "rejected": rejected}

    summary["vendor"] = _run_step(conn, run_id, "vendor_round_trip",
                                  _vendor)

    def _model():
        return powerbi.write_semantic_model(
            work / "powerbi_semantic_model.json")

    _run_step(conn, run_id, "publish_powerbi_model", _model)

    summary["reconciliation"] = _run_step(
        conn, run_id, "reconcile",
        lambda: medallion.reconcile(conn, month))
    ok, detail = summary["reconciliation"]
    if not ok:
        raise RuntimeError("reconciliation failed: %s" % detail)

    summary["alerts"] = _run_step(
        conn, run_id, "health_check",
        lambda: monitoring.health_checks(conn, month, summary["silver"]))
    summary["health"] = monitoring.summarize_alerts(summary["alerts"])

    report = {
        "month": month,
        "bronze_claims": summary["silver"]["bronze_claims"],
        "duplicates_removed": summary["silver"]["duplicates_removed"],
        "silver_claims": summary["silver"]["silver_claims"],
        "quarantined": summary["silver"]["quarantined"],
        "hedis": summary["hedis"],
        "vendor": summary["vendor"],
        "health": summary["health"],
    }
    (work / "hedis_report.json").write_text(json.dumps(report, indent=2))
    lines = ["HEDIS monthly report — %s" % month,
             "bronze claims: %d (duplicates removed: %d)"
             % (report["bronze_claims"], report["duplicates_removed"]),
             "silver claims: %d; quarantined: %d"
             % (report["silver_claims"], report["quarantined"])]
    for r in report["hedis"]:
        lines.append("%s: %d/%d = %.1f%%"
                     % (r["measure"], r["numerator"], r["denominator"],
                        r["rate"] * 100))
    lines.append("vendor round-trip: %d accepted, %d rejected"
                 % (report["vendor"]["accepted"],
                    report["vendor"]["rejected"]))
    lines.append(report["health"])
    (work / "hedis_report.txt").write_text("\n".join(lines) + "\n")
    conn.close()
    return summary
