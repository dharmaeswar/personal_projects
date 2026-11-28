"""Anomaly + governance runner: flag unusual contributions, check controls.

Usage: python run_anomaly.py
Writes anomaly_report.json (flagged contributions for the AI review queue)
and governance_report.json (access checks + control checklist).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from savings_platform import ingest, pipeline, governance  # noqa: E402


def main():
    accounts = ingest.make_accounts()
    batch = ingest.make_contribution_batch(accounts)
    stream = ingest.make_stream_events(accounts)
    silver = pipeline.build_silver(accounts, batch, stream)
    flagged = governance.flag_anomalies(silver["events"])
    anomaly_report = {
        "events_checked": int(
            (silver["events"]["event_type"] == "contribution").sum()),
        "flagged_count": int(len(flagged)),
        "flagged": flagged.to_dict("records"),
    }
    with open("anomaly_report.json", "w") as f:
        json.dump(anomaly_report, f, indent=2, default=str)
    gov_report = {
        "access_checks": {
            "analyst_can_read_holder_id": governance.check_access(
                "analyst", "holder_id"),
            "auditor_can_read_holder_id": governance.check_access(
                "auditor", "holder_id"),
            "analyst_can_read_amount": governance.check_access(
                "analyst", "amount"),
        },
        "controls": governance.control_checklist(),
    }
    with open("governance_report.json", "w") as f:
        json.dump(gov_report, f, indent=2)
    print(f"anomalies flagged: {anomaly_report['flagged_count']} "
          f"of {anomaly_report['events_checked']} contributions")
    print("governance controls satisfied: "
          f"{sum(c['satisfied'] for c in gov_report['controls'])}/"
          f"{len(gov_report['controls'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
