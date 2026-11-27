"""Pipeline runner: bronze -> silver -> gold, ADLS-style partitioned layout.

Writes Parquet tables under lakehouse/ (bronze/, silver/, quarantine/,
gold/daily partitioned by service_date, gold/monthly) plus CSV mirrors the
API layer reads, and a human-readable validation_report.txt.
"""
import json
import os

import pandas as pd

from claims_platform.data import make_claims, make_members
from claims_platform.ml import score_claims, train_paid_model
from claims_platform.transforms import (
    aggregate_daily, aggregate_monthly, dedupe_latest, filter_valid,
    join_member_dim, reconcile, with_derived,
)

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lakehouse")


def run(out_dir=OUT):
    raw = make_claims()
    members = make_members()
    bronze = raw.copy()
    deduped = dedupe_latest(bronze)
    joined = join_member_dim(deduped, members)
    cleansed, quarantined = filter_valid(joined)
    cleansed = with_derived(cleansed)
    gold_daily = aggregate_daily(cleansed)
    gold_monthly = aggregate_monthly(cleansed)
    ok, max_diff = reconcile(cleansed, gold_daily)

    # AI/ML step (Databricks notebook "ScoreClaimsML"): predict paid_amount
    # from billed + cohort, flag high-residual claims for human review.
    model, ml_metrics, residual_std = train_paid_model(cleansed)
    ml_scores = score_claims(model, residual_std, cleansed)
    ml_flagged = int((ml_scores["model_flag"] == "high_residual").sum())

    checks = {
        "schema": list(cleansed.columns) == list(bronze.columns) + ["plan", "state", "enrolled_date", "age_band", "paid_band"],
        "dedup": len(deduped) == len(bronze) - 4,
        "completeness": cleansed["member_id"].notna().all(),
        "non_negative_paid": (cleansed["paid_amount"] >= 0).all(),
        "diag_codes_valid": cleansed["diag_code"].isin({"I25", "M17", "C50", "Z00", "F32"}).all(),
        "arithmetic": ((cleansed["paid_amount"] - (cleansed["billed_amount"] - cleansed["adjustment"])).abs() <= 0.01).all(),
        "reconciliation": ok,
        "ml_scoring": (len(ml_scores) == len(cleansed)
                       and ml_scores["predicted_paid"].notna().all()
                       and ml_flagged < 15),
    }
    summary = {
        "raw": int(len(raw)),
        "duplicates_removed": int(len(bronze) - len(deduped)),
        "quarantined": int(len(quarantined)),
        "cleansed": int(len(cleansed)),
        "gold_daily_rows": int(len(gold_daily)),
        "gold_monthly_rows": int(len(gold_monthly)),
        "total_paid": round(float(cleansed["paid_amount"].sum()), 2),
        "checks_passed": f"{sum(checks.values())}/{len(checks)}",
        "reconciliation_max_diff": max_diff,
        "quarantine_reasons": quarantined["quarantine_reason"].value_counts().to_dict(),
        "ml_test_mae": ml_metrics["test_mae"],
        "ml_test_r2": ml_metrics["test_r2"],
        "ml_flagged_for_review": ml_flagged,
    }

    for name, frame in [("bronze/claims", bronze), ("silver/claims", cleansed),
                        ("quarantine/claims", quarantined),
                        ("gold/daily", gold_daily), ("gold/monthly", gold_monthly),
                        ("gold/model_scores", ml_scores)]:
        d = os.path.join(out_dir, name)
        os.makedirs(d, exist_ok=True)
        frame.to_parquet(os.path.join(d, "data.parquet"), index=False)
        frame.to_csv(os.path.join(d, "data.csv"), index=False)
    # Partitioned gold/daily by service_date, as df.write.partitionBy would do.
    part_dir = os.path.join(out_dir, "gold", "daily_partitioned")
    for date, part in gold_daily.groupby("service_date"):
        d = os.path.join(part_dir, f"service_date={pd.Timestamp(date).date()}")
        os.makedirs(d, exist_ok=True)
        part.to_parquet(os.path.join(d, "data.parquet"), index=False)

    report_path = os.path.join(os.path.dirname(out_dir), "validation_report.txt")
    with open(report_path, "w") as f:
        f.write("Databricks Claims Data Platform — validation report\n")
        f.write(json.dumps(summary, indent=2, default=str) + "\n")
        f.write("checks:\n")
        for name, passed in checks.items():
            f.write(f"  {name}: {'PASS' if passed else 'FAIL'}\n")
    return summary, checks


if __name__ == "__main__":
    summary, checks = run()
    print(json.dumps(summary, indent=2, default=str))
    print({k: ("PASS" if v else "FAIL") for k, v in checks.items()})
