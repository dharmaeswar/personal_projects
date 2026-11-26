"""Data quality: checks over the normalised delivery frame + quarantine.

Checks run on the silver-bound frame before it is published: completeness
(no nulls in required columns), uniqueness (one row per platform /
campaign / day), ranges (spend and conversions non-negative, clicks never
above impressions) and referential integrity (every campaign_id exists in
the campaign dimension). Bad rows are quarantined with a reason, never
dropped silently.

Spark mapping: each check is a DataFrame filter/count; quarantine is a
left-anti join of the failing rows out of the publish set.
"""

from __future__ import annotations

REQUIRED_COLUMNS = [
    "date", "platform", "campaign_id",
    "impressions", "clicks", "spend", "conversions",
]


def run_checks(frame, campaign_ids: set[str]) -> list[dict]:
    """Run every check; each result names the check, rows failing, and pass/fail."""
    results: list[dict] = []
    if frame.empty:
        results.append({"check": "non_empty", "failed_rows": 0, "passed": False,
                        "detail": "frame is empty"})
        return results

    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    results.append({"check": "required_columns", "failed_rows": len(missing),
                    "passed": not missing,
                    "detail": f"missing: {missing}" if missing else "all present"})

    nulls = int(frame[REQUIRED_COLUMNS].isna().sum().sum()) if not missing else 0
    results.append({"check": "completeness", "failed_rows": nulls,
                    "passed": nulls == 0,
                    "detail": f"{nulls} null values in required columns"})

    dupes = int(frame.duplicated(
        subset=["platform", "campaign_id", "date"]).sum())
    results.append({"check": "uniqueness", "failed_rows": dupes,
                    "passed": dupes == 0,
                    "detail": f"{dupes} duplicate platform/campaign/date rows"})

    bad_ranges = int(((frame["spend"] < 0) | (frame["conversions"] < 0)
                      | (frame["clicks"] > frame["impressions"])
                      | (frame["impressions"] < 0)).sum())
    results.append({"check": "ranges", "failed_rows": bad_ranges,
                    "passed": bad_ranges == 0,
                    "detail": f"{bad_ranges} rows break a range rule"})

    unknown = frame[~frame["campaign_id"].isin(campaign_ids)]
    results.append({"check": "referential_integrity",
                    "failed_rows": len(unknown),
                    "passed": len(unknown) == 0,
                    "detail": f"{len(unknown)} rows reference unknown campaigns"})
    return results


def quarantine(frame, campaign_ids: set[str]):
    """Split the frame into clean rows and quarantined rows with reasons."""
    import pandas as pd

    if frame.empty:
        return frame, pd.DataFrame(columns=list(frame.columns) + ["_quarantine_reason"])
    bad_mask = (
        frame[REQUIRED_COLUMNS].isna().any(axis=1)
        | (frame["spend"] < 0)
        | (frame["conversions"] < 0)
        | (frame["clicks"] > frame["impressions"])
        | (frame["impressions"] < 0)
        | (~frame["campaign_id"].isin(campaign_ids))
    )
    clean = frame[~bad_mask].reset_index(drop=True)
    bad = frame[bad_mask].copy()
    reasons = []
    for _, row in bad.iterrows():
        if row[REQUIRED_COLUMNS].isna().any():
            reasons.append("null in a required column")
        elif row["clicks"] > row["impressions"]:
            reasons.append("clicks exceed impressions")
        elif row["spend"] < 0 or row["conversions"] < 0:
            reasons.append("negative spend or conversions")
        elif row["campaign_id"] not in campaign_ids:
            reasons.append("unknown campaign_id")
        else:
            reasons.append("failed a quality check")
    bad["_quarantine_reason"] = reasons
    return clean, bad.reset_index(drop=True)
