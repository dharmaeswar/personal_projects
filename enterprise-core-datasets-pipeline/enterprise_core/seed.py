"""Synthetic seed data for the four enterprise feeds.

All data is synthetic and seeded (seed 42). No real company, customer, or
booking data is used, and nothing here is a claim about any real institution.

The seed plants defects on purpose so the contract, dedupe, and quarantine
paths run on every execution:
- ai_usage: 4 duplicate event_ids (re-delivered batches, deduped not quarantined),
  3 null teams, 2 negative token counts, 2 unknown tools, 1 future date
  (8 quarantined in total).
- jira_issues: 2 issues in an unknown project, 1 negative story points,
  1 status outside the allowed set.
- bookings: 1 row with revenue above GBV, 1 negative hosting cost.
- payments: 2 duplicate txn_ids (re-delivered gateway batches, deduped not
  quarantined), 2 negative amounts, 1 unknown payment method, 1 settled
  amount above the authorised amount, 1 failed txn carrying a settled
  amount, 1 future date (6 quarantined in total).
"""

import random
from datetime import date, timedelta

TOOLS = ["copilot-pro", "code-assistant", "doc-summarizer", "support-drafting"]
TEAMS = ["platform", "payments", "trust", "growth", "finance"]
PROJECTS = ["CORE", "DATA", "BIZ"]
PAYMENT_METHODS = ["card", "ach", "wire", "wallet"]
PAYMENT_STATUSES = ["authorized", "captured", "settled", "failed"]
START = date(2026, 10, 1)
DAYS = 56  # 2026-10-01 .. 2026-11-25

# Contracted unit price per 1k tokens, by tool and effective date. Prices change
# on 2026-11-01; dim_tool keeps both versions (SCD Type 2) so a fact always
# joins the price in force on its event date.
PRICE_HISTORY = {
    "copilot-pro": [("2026-10-01", 3.00), ("2026-11-01", 2.50)],
    "code-assistant": [("2026-10-01", 1.50), ("2026-11-01", 1.25)],
    "doc-summarizer": [("2026-10-01", 1.00)],
    "support-drafting": [("2026-10-01", 2.00)],
}


def price_on(tool, day_iso):
    price = None
    for effective, value in PRICE_HISTORY[tool]:
        if day_iso >= effective:
            price = value
    return price


def _dates():
    return [START + timedelta(days=i) for i in range(DAYS)]


def seed_ai_usage(rng):
    rows = []
    for i, day in enumerate(_dates()):
        for tool in TOOLS:
            for team in TEAMS:
                n = rng.randint(2, 6)
                for _ in range(n):
                    tokens_in = rng.randint(500, 40_000)
                    tokens_out = rng.randint(200, 12_000)
                    price = price_on(tool, day.isoformat())
                    rows.append({
                        "event_id": f"ai-{i:02d}-{tool}-{team}-{rng.randint(0, 99999):05d}",
                        "event_date": day.isoformat(),
                        "tool_name": tool,
                        "team": team,
                        "user_id": f"u-{rng.randint(1000, 9999)}",
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                        "cost_usd": round((tokens_in + tokens_out) * price / 1000.0, 4),
                    })
    # Planted defects (12 rows).
    base = list(rows[:4])
    for r in base:  # 4 duplicates: same event_id, re-delivered
        rows.append(dict(r))
    for k in range(3):
        bad = dict(rows[10 + k]); bad["event_id"] = f"ai-bad-null-{k}"; bad["team"] = None
        rows.append(bad)
    for k in range(2):
        bad = dict(rows[20 + k]); bad["event_id"] = f"ai-bad-neg-{k}"; bad["tokens_in"] = -5
        rows.append(bad)
    for k in range(2):
        bad = dict(rows[30 + k]); bad["event_id"] = f"ai-bad-tool-{k}"; bad["tool_name"] = "mystery-tool"
        rows.append(bad)
    bad = dict(rows[40]); bad["event_id"] = "ai-bad-date-0"; bad["event_date"] = "2026-12-01"
    rows.append(bad)
    rng.shuffle(rows)
    return rows


def seed_jira(rng):
    rows = []
    for n in range(240):
        created = START + timedelta(days=rng.randint(0, 45))
        updated = created + timedelta(days=rng.randint(0, 10))
        rows.append({
            "issue_key": f"{rng.choice(PROJECTS)}-{1000 + n}",
            "project_key": rng.choice(PROJECTS),
            "issue_type": rng.choice(["Story", "Task", "Bug", "Epic"]),
            "status": rng.choice(["Open", "In Progress", "Done", "Blocked"]),
            "story_points": rng.choice([0, 1, 2, 3, 5, 8, 13]),
            "team": rng.choice(TEAMS),
            "created_date": created.isoformat(),
            "updated_date": min(updated, date(2026, 11, 25)).isoformat(),
        })
    for k in range(2):  # unknown project
        bad = dict(rows[k]); bad["issue_key"] = f"XXXX-{k}"; bad["project_key"] = "XXXX"
        rows.append(bad)
    bad = dict(rows[5]); bad["issue_key"] = "CORE-9991"; bad["story_points"] = -3
    rows.append(bad)
    bad = dict(rows[6]); bad["issue_key"] = "CORE-9992"; bad["status"] = "Shipped"
    rows.append(bad)
    return rows


def seed_bookings(rng):
    rows = []
    for i, day in enumerate(_dates()):
        gbv = round(rng.uniform(1_200_000, 2_400_000), 2)
        revenue = round(gbv * rng.uniform(0.10, 0.14), 2)
        rows.append({
            "booking_id": f"bk-{day.isoformat()}",
            "booking_date": day.isoformat(),
            "gbv_usd": gbv,
            "revenue_usd": revenue,
            "hosting_cost_usd": round(revenue * rng.uniform(0.18, 0.25), 2),
            "support_cost_usd": round(revenue * rng.uniform(0.08, 0.12), 2),
            "payment_cost_usd": round(gbv * rng.uniform(0.015, 0.025), 2),
        })
    bad = dict(rows[3]); bad["booking_id"] = "bk-bad-0"; bad["revenue_usd"] = bad["gbv_usd"] + 1.0
    rows.append(bad)
    bad = dict(rows[4]); bad["booking_id"] = "bk-bad-1"; bad["hosting_cost_usd"] = -50.0
    rows.append(bad)
    return rows


def seed_payments(rng):
    """Payment transactions from a gateway feed.

    A transaction moves authorized -> captured -> settled; a failed txn
    settles nothing. settled_amount_usd is the amount that reached the
    settlement account; settlement_lag_days is txn_date -> settlement date.
    """
    rows = []
    for i, day in enumerate(_dates()):
        for method in PAYMENT_METHODS:
            n = rng.randint(3, 8)
            for _ in range(n):
                status = rng.choice(PAYMENT_STATUSES + ["settled", "settled"])
                amount = round(rng.uniform(25.0, 4_800.0), 2)
                if status == "settled":
                    settled = round(amount * rng.uniform(0.97, 1.0), 2)
                    lag = rng.randint(1, 2)
                elif status == "captured":
                    settled = 0.0
                    lag = 0
                else:  # authorized or failed: nothing settled yet
                    settled = 0.0
                    lag = 0
                rows.append({
                    "txn_id": f"pay-{i:02d}-{method}-{rng.randint(0, 99999):05d}",
                    "txn_date": day.isoformat(),
                    "payment_method": method,
                    "status": status,
                    "amount_usd": amount,
                    "settled_amount_usd": settled,
                    "settlement_lag_days": lag,
                })
    # Planted defects (8 rows, 6 quarantined + 2 deduped).
    base = list(rows[:2])
    for r in base:  # 2 duplicates: same txn_id, re-delivered gateway batch
        rows.append(dict(r))
    bad = dict(rows[10]); bad["txn_id"] = "pay-bad-neg-0"; bad["amount_usd"] = -12.50
    rows.append(bad)
    bad = dict(rows[11]); bad["txn_id"] = "pay-bad-neg-1"; bad["settled_amount_usd"] = -5.0
    rows.append(bad)
    bad = dict(rows[12]); bad["txn_id"] = "pay-bad-method-0"; bad["payment_method"] = "crypto"
    rows.append(bad)
    bad = dict(rows[13]); bad["txn_id"] = "pay-bad-settled-0"; bad["status"] = "settled"
    bad["settled_amount_usd"] = bad["amount_usd"] + 10.0
    rows.append(bad)
    bad = dict(rows[14]); bad["txn_id"] = "pay-bad-failed-0"; bad["status"] = "failed"
    bad["settled_amount_usd"] = 100.0
    rows.append(bad)
    bad = dict(rows[15]); bad["txn_id"] = "pay-bad-date-0"; bad["txn_date"] = "2026-12-01"
    rows.append(bad)
    rng.shuffle(rows)
    return rows


def seed_all(seed=42):
    rng = random.Random(seed)
    return {
        "ai_usage": seed_ai_usage(rng),
        "jira_issues": seed_jira(rng),
        "bookings": seed_bookings(rng),
        "payments": seed_payments(rng),
    }
