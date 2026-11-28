"""Run the Fin deployment impact analysis end to end and write outputs.

Usage: python run_analysis.py [--db PATH]
Writes outputs/impact_summary.txt and outputs/per_customer.csv.
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fin_impact import data, deploy, report, sql_analysis  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=":memory:",
                        help="SQLite path (default in-memory demo)")
    args = parser.parse_args()

    convs = data.make_conversations()
    conn = sql_analysis.connect(args.db)
    sql_analysis.load(conn, convs)
    metrics = sql_analysis.metrics(conn)
    channels = sql_analysis.by_channel(conn)
    handle_test, esc_uplift = report.compare_arms(convs)

    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "outputs")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "impact_summary.txt"), "w") as fh:
        fh.write(report.customer_summary("all customers", metrics,
                                         handle_test, esc_uplift))
        fh.write("\nProduct feedback:\n")
        for note in report.product_feedback(channels, metrics):
            fh.write(f"- {note}\n")
    with open(os.path.join(outdir, "per_customer.csv"), "w",
              newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["customer", "period", "conversations",
                         "resolution_rate", "mean_handle_minutes",
                         "mean_csat", "escalation_rate"])
        for customer in data.CUSTOMERS:
            m = sql_analysis.metrics(conn, customer)
            for period in ("before", "after"):
                row = m[period]
                writer.writerow([customer, period, row["conversations"],
                                 row["resolution_rate"],
                                 row["mean_handle_minutes"],
                                 row["mean_csat"],
                                 row["escalation_rate"]])

    readiness = deploy.readiness_score({
        "volume_baseline": True, "kb_coverage": True,
        "escalation_path": True, "csat_baseline": True,
        "owner_named": False})
    print(f"Conversations: {len(convs)}")
    print(f"Overall: {metrics}")
    print(f"Handle-time test: {handle_test}")
    print(f"Resolution uplift: {esc_uplift}")
    print(f"Readiness example: {readiness}")
    print(f"Outputs written to {outdir}")


if __name__ == "__main__":
    main()
