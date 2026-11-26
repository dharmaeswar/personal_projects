"""Source contracts for the three enterprise feeds.

A contract is the agreement a pipeline makes with a source: required fields,
types, allowed values, and ranges. Rows that break the contract are
quarantined with a reason, never silently loaded. This is the "source
contract" step the Enterprise Core Datasets team applies before a feed
becomes a reusable dataset.
"""

CONTRACTS = {
    "ai_usage": {
        "required": ["event_id", "event_date", "tool_name", "team", "user_id",
                     "tokens_in", "tokens_out", "cost_usd"],
        "types": {"event_id": str, "event_date": str, "tool_name": str,
                  "team": str, "user_id": str, "tokens_in": int,
                  "tokens_out": int, "cost_usd": float},
        "allowed": {"tool_name": ["copilot-pro", "code-assistant", "doc-summarizer",
                                  "support-drafting"]},
        "ranges": {"tokens_in": (0, 1_000_000), "tokens_out": (0, 1_000_000),
                   "cost_usd": (0.0, 10_000.0)},
        "date_range": ("2026-10-01", "2026-11-25"),
    },
    "jira_issues": {
        "required": ["issue_key", "project_key", "issue_type", "status",
                     "story_points", "team", "created_date", "updated_date"],
        "types": {"issue_key": str, "project_key": str, "issue_type": str,
                  "status": str, "story_points": int, "team": str,
                  "created_date": str, "updated_date": str},
        "allowed": {"issue_type": ["Story", "Task", "Bug", "Epic"],
                    "status": ["Open", "In Progress", "Done", "Blocked"],
                    "project_key": ["CORE", "DATA", "BIZ"]},
        "ranges": {"story_points": (0, 21)},
        "date_range": ("2026-10-01", "2026-11-25"),
    },
    "bookings": {
        "required": ["booking_id", "booking_date", "gbv_usd", "revenue_usd",
                     "hosting_cost_usd", "support_cost_usd", "payment_cost_usd"],
        "types": {"booking_id": str, "booking_date": str, "gbv_usd": float,
                  "revenue_usd": float, "hosting_cost_usd": float,
                  "support_cost_usd": float, "payment_cost_usd": float},
        "allowed": {},
        "ranges": {"gbv_usd": (0.0, 5_000_000.0), "revenue_usd": (0.0, 5_000_000.0),
                   "hosting_cost_usd": (0.0, 500_000.0),
                   "support_cost_usd": (0.0, 500_000.0),
                   "payment_cost_usd": (0.0, 500_000.0)},
        "date_range": ("2026-10-01", "2026-11-25"),
    },
}


def validate(feed, rows):
    """Check rows (list of dicts) against the feed contract.

    Returns (good, quarantined) where quarantined rows carry a ``_reason``
    field naming the broken rule. Mirrors a Spark ``filter`` with the same
    predicates, applied before any write lands.
    """
    contract = CONTRACTS[feed]
    good, quarantined = [], []
    for row in rows:
        reason = None
        for field in contract["required"]:
            if field not in row or row[field] is None or row[field] == "":
                reason = f"missing {field}"
                break
        if reason is None:
            for field, typ in contract["types"].items():
                value = row[field]
                if typ is int and isinstance(value, bool):
                    reason = f"{field} must be int"
                    break
                if typ is int and not isinstance(value, int):
                    reason = f"{field} must be int"
                    break
                if typ is float and not isinstance(value, (int, float)):
                    reason = f"{field} must be numeric"
                    break
                if typ is str and not isinstance(value, str):
                    reason = f"{field} must be str"
                    break
        if reason is None:
            for field, allowed in contract["allowed"].items():
                if row[field] not in allowed:
                    reason = f"{field}={row[field]!r} not allowed"
                    break
        if reason is None:
            for field, (low, high) in contract["ranges"].items():
                if not (low <= row[field] <= high):
                    reason = f"{field}={row[field]} outside [{low}, {high}]"
                    break
        if reason is None:
            low, high = contract["date_range"]
            date_field = "event_date" if feed == "ai_usage" else (
                "created_date" if feed == "jira_issues" else "booking_date")
            if not (low <= str(row[date_field]) <= high):
                reason = f"{date_field}={row[date_field]} outside [{low}, {high}]"
        if reason is None and feed == "bookings" and row["revenue_usd"] > row["gbv_usd"]:
            reason = "revenue_usd exceeds gbv_usd"
        if reason is None:
            good.append(row)
        else:
            bad = dict(row)
            bad["_reason"] = reason
            quarantined.append(bad)
    return good, quarantined
