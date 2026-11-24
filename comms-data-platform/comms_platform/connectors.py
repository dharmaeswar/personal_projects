"""Source connectors — internal comms system + vendor engagement API.

This is a local model of the two ingest sources in the real Comms Tech
platform: an internal system that holds messages/campaigns and a vendor API
that returns engagement metrics (opens, clicks) per campaign.

All data is synthetic and seeded (seed 42). No real company, campaign, or
engagement data is used. No network calls are made: the vendor API is
simulated in-process, including pagination, a transient failure on one page
(to exercise retry), and a rate-limit counter.
"""

from __future__ import annotations

import random

CAMPAIGNS = [
    ("CMP-101", "Q4 All-Hands Announcement", "email"),
    ("CMP-102", "Security Awareness Newsletter", "email"),
    ("CMP-103", "New Hire Onboarding Series", "portal"),
    ("CMP-104", "Benefits Open Enrollment", "email"),
    ("CMP-105", "Engineering All-Hands Recap", "portal"),
]

# Bad rows planted on purpose (mirrors the lakehouse validation story):
#  - one duplicate message id
#  - one message with a null campaign id
#  - one message dated in the future
#  - one metric row with negative opens
#  - one metric row for an unknown campaign
BAD_MESSAGE_IDS = {"MSG-1007"}  # duplicate of MSG-1003's payload shape


def _seeded_messages():
    rng = random.Random(42)
    rows = []
    for i in range(12):
        campaign = CAMPAIGNS[i % len(CAMPAIGNS)]
        rows.append(
            {
                "message_id": f"MSG-{1001 + i}",
                "campaign_id": campaign[0],
                "campaign_name": campaign[1],
                "channel": campaign[2],
                "subject": f"{campaign[1]} — update {i + 1}",
                "send_date": f"2026-11-{10 + (i % 10):02d}",
                "audience_size": rng.randint(800, 5200),
            }
        )
    # Planted bad rows.
    rows.append(dict(rows[2], message_id="MSG-1003"))  # duplicate message_id
    rows.append(
        {
            "message_id": "MSG-1013",
            "campaign_id": None,
            "campaign_name": "Orphan Message",
            "channel": "email",
            "subject": "Orphan — update 1",
            "send_date": "2026-11-15",
            "audience_size": 1200,
        }
    )
    rows.append(
        {
            "message_id": "MSG-1014",
            "campaign_id": "CMP-102",
            "campaign_name": "Security Awareness Newsletter",
            "channel": "email",
            "subject": "Future-dated — update 1",
            "send_date": "2027-03-01",
            "audience_size": 900,
        }
    )
    return rows


def _seeded_metrics():
    rng = random.Random(7)
    rows = []
    for i in range(12):
        campaign = CAMPAIGNS[i % len(CAMPAIGNS)]
        rows.append(
            {
                "campaign_id": campaign[0],
                "event_date": f"2026-11-{10 + (i % 10):02d}",
                "opens": rng.randint(200, 2400),
                "clicks": rng.randint(10, 320),
                "unsubscribes": rng.randint(0, 12),
            }
        )
    rows.append(
        {
            "campaign_id": "CMP-101",
            "event_date": "2026-11-12",
            "opens": -5,
            "clicks": 3,
            "unsubscribes": 0,
        }
    )
    rows.append(
        {
            "campaign_id": "CMP-999",
            "event_date": "2026-11-12",
            "opens": 40,
            "clicks": 2,
            "unsubscribes": 0,
        }
    )
    return rows


class InternalCommsSource:
    """Simulated internal system: returns message/campaign records."""

    def __init__(self):
        self._rows = _seeded_messages()

    def fetch_messages(self):
        """Return all message rows (a full daily extract)."""
        return [dict(r) for r in self._rows]


class TransientVendorError(RuntimeError):
    """A retryable vendor-API failure (5xx / timeout)."""


class VendorAPIClient:
    """Simulated paginated vendor engagement API.

    Pages are 5 rows each. Page 2 fails once with a transient error, then
    succeeds on retry — the pipeline's retry logic is tested against this.
    A rate-limit counter records calls; the client refuses after 20 calls
    in one run (a local stand-in for a vendor quota).
    """

    PAGE_SIZE = 5
    RATE_LIMIT = 20

    def __init__(self):
        self._rows = _seeded_metrics()
        self._failed_once = False
        self.calls = 0

    def fetch_page(self, page_token=None):
        self.calls += 1
        if self.calls > self.RATE_LIMIT:
            raise TransientVendorError("vendor rate limit exceeded")
        start = int(page_token) if page_token else 0
        if start == self.PAGE_SIZE and not self._failed_once:
            self._failed_once = True
            raise TransientVendorError("vendor 503: transient failure")
        page = self._rows[start : start + self.PAGE_SIZE]
        next_token = (
            str(start + self.PAGE_SIZE)
            if start + self.PAGE_SIZE < len(self._rows)
            else None
        )
        return {"rows": [dict(r) for r in page], "next_page_token": next_token}


def fetch_all_vendor_metrics(client, max_retries=3):
    """Fetch every vendor page, retrying transient failures per page."""
    rows = []
    token = None
    while True:
        attempts = 0
        while True:
            try:
                page = client.fetch_page(token)
                break
            except TransientVendorError:
                attempts += 1
                if attempts > max_retries:
                    raise
        rows.extend(page["rows"])
        token = page["next_page_token"]
        if token is None:
            return rows
