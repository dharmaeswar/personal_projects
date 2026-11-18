"""Synthetic advertising data, seeded and deterministic.

Three tables:

- ``campaigns`` — 12 campaigns (advertiser, channel, budget window).
- ``ads`` — 30 ads, each belonging to one campaign.
- ``events`` — 240 clean ad-event rows (one ad, one hour each) plus 14
  deliberately planted bad rows, so the quality checks have real
  violations to catch. Two of the clean rows are late-arriving events
  (September dates, before the October watermark): they are valid data
  that arrived late, so they belong in silver, flagged, not quarantined.

All data is synthetic. No real advertiser, campaign, or spend data is used.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

SEED = 42

MIN_EVENT_TS = "2026-09-01T00:00:00"
MAX_EVENT_TS = "2026-11-16T23:59:59"
# Events dated before this arrived after the watermark: late, but valid.
WATERMARK_TS = "2026-10-01T00:00:00"

CHANNELS = ["sponsored_search", "display", "video"]

# event_id -> violation planted on that appended row.
PLANTED_VIOLATIONS = {
    "duplicate event_id": 3,
    "null campaign_id": 3,
    "negative spend": 2,
    "clicks exceed impressions": 2,
    "unknown ad_id": 2,
    "future event_ts": 1,
    "wrong spend": 1,
}

CAMPAIGN_FIELDS = [
    "campaign_id",
    "advertiser",
    "channel",
    "start_date",
    "end_date",
    "daily_budget_usd",
]

AD_FIELDS = ["ad_id", "campaign_id", "format", "placement"]

EVENT_FIELDS = [
    "event_id",
    "ad_id",
    "campaign_id",
    "event_ts",
    "impressions",
    "clicks",
    "cpc_usd",
    "spend_usd",
]


def generate_campaigns() -> list[dict]:
    rng = random.Random(SEED)
    advertisers = [
        "Northwind Outdoors",
        "BluePeak Electronics",
        "Harbor Groceries",
        "Summit Fitness",
        "Copperline Tools",
        "Meadow Toys",
    ]
    campaigns = []
    for i in range(12):
        campaigns.append(
            {
                "campaign_id": f"C{i + 1:03d}",
                "advertiser": advertisers[i % len(advertisers)],
                "channel": CHANNELS[i % len(CHANNELS)],
                "start_date": "2026-09-01",
                "end_date": "2026-11-30",
                "daily_budget_usd": round(rng.uniform(200.0, 2000.0), 2),
            }
        )
    return campaigns


def generate_ads(campaigns: list[dict]) -> list[dict]:
    rng = random.Random(SEED + 1)
    formats = ["banner", "video", "sponsored_listing"]
    placements = ["search_results", "product_page", "home_feed"]
    ads = []
    for i in range(30):
        campaign = campaigns[i % len(campaigns)]
        ads.append(
            {
                "ad_id": f"AD{i + 1:04d}",
                "campaign_id": campaign["campaign_id"],
                "format": formats[rng.randrange(len(formats))],
                "placement": placements[rng.randrange(len(placements))],
            }
        )
    return ads


def _clean_event(rng: random.Random, i: int, ads: list[dict], late: bool) -> dict:
    ad = ads[rng.randrange(len(ads))]
    if late:
        day = datetime(2026, 9, 10) + timedelta(days=rng.randrange(0, 15))
    else:
        day = datetime(2026, 10, 1) + timedelta(days=rng.randrange(0, 47))
    ts = day + timedelta(hours=rng.randrange(0, 24))
    impressions = rng.randrange(50, 5001)
    clicks = rng.randrange(0, max(1, impressions // 10 + 1))
    cpc = round(rng.uniform(0.20, 3.50), 2)
    return {
        "event_id": f"E{i + 1:04d}",
        "ad_id": ad["ad_id"],
        "campaign_id": ad["campaign_id"],
        "event_ts": ts.strftime("%Y-%m-%dT%H:%M:%S"),
        "impressions": impressions,
        "clicks": clicks,
        "cpc_usd": cpc,
        "spend_usd": round(clicks * cpc, 2),
    }


def generate_events(
    campaigns: list[dict], ads: list[dict]
) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (clean_events, planted_bad_rows, all_bronze_events).

    240 clean rows (2 of them late-arriving) + 14 planted bad rows = 254.
    """
    rng = random.Random(SEED + 2)
    clean = []
    for i in range(240):
        clean.append(_clean_event(rng, i, ads, late=(i in (5, 137))))

    bad: list[dict] = []

    def _base(idx: int) -> dict:
        row = dict(clean[idx])
        return row

    # 3 duplicate event_ids (exact copies of clean rows, new list entries).
    for idx in (10, 50, 120):
        bad.append(_base(idx))
    # 3 null campaign_ids.
    for idx in (20, 60, 130):
        row = _base(idx)
        row["event_id"] = f"E9{idx:03d}"
        row["campaign_id"] = None
        bad.append(row)
    # 2 negative spend (clicks 0, cpc 0.00, so arithmetic also disagrees).
    for idx in (30, 70):
        row = _base(idx)
        row["event_id"] = f"E9{idx:03d}"
        row["clicks"] = 0
        row["cpc_usd"] = 0.00
        row["spend_usd"] = -5.00
        bad.append(row)
    # 2 clicks exceed impressions.
    for idx in (40, 80):
        row = _base(idx)
        row["event_id"] = f"E9{idx:03d}"
        row["impressions"] = 10
        row["clicks"] = 25
        row["cpc_usd"] = 1.00
        row["spend_usd"] = 25.00
        bad.append(row)
    # 2 unknown ad_ids.
    for idx in (90, 100):
        row = _base(idx)
        row["event_id"] = f"E9{idx:03d}"
        row["ad_id"] = "AD9999"
        bad.append(row)
    # 1 future event_ts.
    row = _base(110)
    row["event_id"] = "E9110"
    row["event_ts"] = "2026-12-25T10:00:00"
    bad.append(row)
    # 1 wrong spend (spend does not equal clicks * cpc).
    row = _base(140)
    row["event_id"] = "E9140"
    row["clicks"] = 40
    row["cpc_usd"] = 1.50
    row["spend_usd"] = 999.99
    bad.append(row)

    assert len(bad) == sum(PLANTED_VIOLATIONS.values()) == 14
    return clean, bad, clean + bad


def generate_all() -> dict[str, list[dict]]:
    """Return the full bronze dataset: campaigns, ads, events."""
    campaigns = generate_campaigns()
    ads = generate_ads(campaigns)
    clean, bad, events = generate_events(campaigns, ads)
    return {
        "campaigns": campaigns,
        "ads": ads,
        "events": events,
        "clean_events": clean,
        "planted_bad_rows": bad,
    }
