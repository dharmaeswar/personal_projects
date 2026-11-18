"""Synthetic security telemetry for the security-analytics pipeline.

All data is synthetic and seeded (deterministic). No real users, hosts,
logins, or vulnerabilities are involved. A small number of bad rows are
planted on purpose so the data-quality checks have something to catch;
the counts are documented in the README.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

AS_OF = datetime(2026, 11, 18, 0, 0, 0)
WATERMARK = datetime(2026, 10, 1, 0, 0, 0)
SEED = 20261113

FIRST_NAMES = [
    "Ava", "Liam", "Maya", "Noah", "Priya", "Ethan", "Zoe", "Lucas",
    "Amara", "Owen", "Nina", "Felix", "Sara", "Diego", "Hana", "Marcus",
    "Leah", "Omar", "Tara", "Victor", "Iris", "Sam", "Rosa", "Kofi",
    "Elena", "Raj", "Mia", "Tom", "Aisha", "Ben", "Lena", "Chris",
    "Dana", "Yuki", "Paul", "Nadia", "Alex", "Grace", "Ivan", "June",
]
LAST_NAMES = [
    "Patel", "Kim", "Garcia", "Novak", "Sharma", "Chen", "Okafor",
    "Silva", "Meyer", "Ali", "Rossi", "Tanaka", "Dubois", "Costa",
    "Singh", "Murphy", "Khan", "Fischer", "Lopez", "Ivanov",
]
DEPARTMENTS = ["Engineering", "Security", "Finance", "People", "Product", "IT"]
COUNTRIES = [
    ("US", "New York"),
    ("US", "San Francisco"),
    ("GB", "London"),
    ("DE", "Berlin"),
    ("JP", "Tokyo"),
    ("IN", "Bengaluru"),
    ("CA", "Toronto"),
]
AUDIT_ACTIONS = [
    "console_login",
    "api_call",
    "policy_change",
    "role_assigned",
    "key_rotated",
    "config_change",
]
FINDING_TITLES = {
    "critical": ["Unpatched remote-code-execution flaw", "Exposed admin console"],
    "high": ["Outdated TLS configuration", "Overly broad IAM role", "Missing disk encryption"],
    "medium": ["Weak password policy on service account", "Unrotated API key", "Open non-standard port"],
    "low": ["Missing security header", "Verbose error messages", "Stale documentation link"],
}
# Remediation SLA in days, by severity.
SLA_DAYS = {"critical": 7, "high": 14, "medium": 30, "low": 60}


def _random_ts(rng: random.Random, start: datetime, end: datetime) -> datetime:
    span = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randrange(span))


def generate_identities(rng: random.Random) -> list[dict]:
    """40 synthetic identities. 8 are privileged; 2 of those have MFA off
    and 2 are dormant (> 90 days since last login)."""
    identities = []
    for i in range(40):
        privileged = i % 5 == 0
        mfa_enabled = False if i in (5, 15, 7) else True
        if i == 0:
            last_login_days = 120
        elif i == 20:
            last_login_days = 100
        else:
            last_login_days = rng.randrange(0, 31)
        home_country, home_city = COUNTRIES[i % len(COUNTRIES)]
        identities.append(
            {
                "identity_id": f"id-{i + 1:03d}",
                "name": f"{FIRST_NAMES[i]} {LAST_NAMES[i % len(LAST_NAMES)]}",
                "email": f"{FIRST_NAMES[i].lower()}.{LAST_NAMES[i % len(LAST_NAMES)].lower()}@example.internal",
                "department": DEPARTMENTS[i % len(DEPARTMENTS)],
                "privileged": privileged,
                "mfa_enabled": mfa_enabled,
                "last_login_days_ago": last_login_days,
                "status": "active",
                "home_country": home_country,
                "home_city": home_city,
            }
        )
    return identities


def generate_assets(rng: random.Random, identities: list[dict]) -> list[dict]:
    """30 synthetic assets, each owned by an identity."""
    types = ["server", "laptop", "database", "workstation"]
    assets = []
    for i in range(30):
        assets.append(
            {
                "asset_id": f"asset-{i + 1:03d}",
                "hostname": f"host-{i + 1:02d}.example.internal",
                "asset_type": types[i % len(types)],
                "owner_identity_id": identities[i % len(identities)]["identity_id"],
                "criticality": "high" if i % 4 == 0 else ("medium" if i % 2 == 0 else "low"),
                "last_seen_days_ago": rng.randrange(0, 6),
            }
        )
    return assets


def generate_login_events(rng: random.Random, identities: list[dict]) -> list[dict]:
    """316 login events: 300 ordinary rows plus 16 planted rows.

    Planted: 2 duplicate event_ids, 2 null identity_ids, 2 unknown
    identity_ids, 2 late events (before the Oct 1 watermark), 2 rows
    forming one impossible-travel pair, and 6 failed logins forming one
    brute-force burst.
    """
    start = datetime(2026, 11, 1, 0, 0, 0)
    end = datetime(2026, 11, 17, 23, 59, 59)
    by_id = {ident["identity_id"]: ident for ident in identities}
    events: list[dict] = []
    for n in range(300):
        ident = rng.choice(identities)
        # Ordinary logins come from the identity's home country; only the
        # planted impossible-travel pair crosses countries quickly.
        success = rng.random() < 0.90
        events.append(
            {
                "event_id": f"login-{n + 1:04d}",
                "identity_id": ident["identity_id"],
                "ts": _random_ts(rng, start, end),
                "ip": f"203.0.113.{rng.randrange(1, 255)}",
                "country": ident["home_country"],
                "city": ident["home_city"],
                "success": success,
                "mfa_used": bool(ident["mfa_enabled"] and success),
            }
        )

    # 2 duplicate event_ids (same id, same content, re-delivered).
    events.append(dict(events[9]))
    events.append(dict(events[49]))

    # 2 rows with a null identity reference.
    for n in (901, 902):
        events.append(
            {
                "event_id": f"login-{n}",
                "identity_id": None,
                "ts": _random_ts(rng, start, end),
                "ip": "203.0.113.200",
                "country": "US",
                "city": "New York",
                "success": True,
                "mfa_used": False,
            }
        )

    # 2 rows referencing identities that do not exist.
    for n, unknown in ((903, "id-999"), (904, "id-998")):
        events.append(
            {
                "event_id": f"login-{n}",
                "identity_id": unknown,
                "ts": _random_ts(rng, start, end),
                "ip": "203.0.113.201",
                "country": "US",
                "city": "New York",
                "success": True,
                "mfa_used": False,
            }
        )

    # 2 late-arriving rows (dated September, before the watermark).
    for n, day in ((905, 15), (906, 20)):
        events.append(
            {
                "event_id": f"login-{n}",
                "identity_id": "id-001",
                "ts": datetime(2026, 9, day, 10, 0, 0),
                "ip": "203.0.113.202",
                "country": "US",
                "city": "New York",
                "success": True,
                "mfa_used": True,
            }
        )

    # Impossible travel: id-003 logs in from New York and Tokyo 30 min apart.
    events.append(
        {
            "event_id": "login-907",
            "identity_id": "id-003",
            "ts": datetime(2026, 11, 10, 9, 0, 0),
            "ip": "203.0.113.10",
            "country": "US",
            "city": "New York",
            "success": True,
            "mfa_used": True,
        }
    )
    events.append(
        {
            "event_id": "login-908",
            "identity_id": "id-003",
            "ts": datetime(2026, 11, 10, 9, 30, 0),
            "ip": "203.0.113.11",
            "country": "JP",
            "city": "Tokyo",
            "success": True,
            "mfa_used": True,
        }
    )

    # Brute-force burst: 6 failed logins for id-007 within 8 minutes.
    base = datetime(2026, 11, 12, 14, 0, 0)
    for k in range(6):
        events.append(
            {
                "event_id": f"login-{909 + k}",
                "identity_id": "id-007",
                "ts": base + timedelta(minutes=k),
                "ip": "198.51.100.44",
                "country": "US",
                "city": "New York",
                "success": False,
                "mfa_used": False,
            }
        )
    return events


def generate_audit_events(rng: random.Random, identities, assets) -> list[dict]:
    """153 cloud audit events: 150 ordinary rows plus 3 planted rows
    (1 unknown asset, 1 unknown identity, 1 duplicate event_id)."""
    start = datetime(2026, 11, 1, 0, 0, 0)
    end = datetime(2026, 11, 17, 23, 59, 59)
    events: list[dict] = []
    for n in range(150):
        events.append(
            {
                "event_id": f"audit-{n + 1:04d}",
                "identity_id": rng.choice(identities)["identity_id"],
                "asset_id": rng.choice(assets)["asset_id"],
                "action": rng.choice(AUDIT_ACTIONS),
                "ts": _random_ts(rng, start, end),
                "result": "success" if rng.random() < 0.95 else "failure",
            }
        )
    events.append(
        {
            "event_id": "audit-901",
            "identity_id": "id-002",
            "asset_id": "asset-999",
            "action": "config_change",
            "ts": datetime(2026, 11, 5, 12, 0, 0),
            "result": "success",
        }
    )
    events.append(
        {
            "event_id": "audit-902",
            "identity_id": "id-997",
            "asset_id": "asset-001",
            "action": "api_call",
            "ts": datetime(2026, 11, 6, 12, 0, 0),
            "result": "success",
        }
    )
    events.append(dict(events[4]))  # duplicate event_id
    return events


def generate_findings(rng: random.Random, assets: list[dict]) -> list[dict]:
    """60 vulnerability findings. 20 are remediated; 40 are open.
    6 of the open ones are overdue (due before Nov 18). Two rows are
    planted bad data: find-059 has due_date before discovered_date,
    find-060 references an unknown asset."""
    severities = (
        ["critical"] * 5 + ["high"] * 15 + ["medium"] * 25 + ["low"] * 15
    )
    rng.shuffle(severities)
    findings: list[dict] = []
    for n in range(60):
        severity = severities[n]
        discovered = datetime(2026, 10, 1, 0, 0, 0) + timedelta(
            days=rng.randrange(0, 41)
        )
        due = discovered + timedelta(days=SLA_DAYS[severity])
        remediated = n < 20
        if remediated:
            remediated_date = discovered + timedelta(days=rng.randrange(2, 13))
            status = "remediated"
        else:
            remediated_date = None
            status = "open"
            # Keep ordinary open findings due on or after the as-of date
            # so only the planted ones are overdue.
            if due < AS_OF:
                due = AS_OF + timedelta(days=rng.randrange(1, 21))
        findings.append(
            {
                "finding_id": f"find-{n + 1:03d}",
                "asset_id": rng.choice(assets)["asset_id"],
                "severity": severity,
                "title": rng.choice(FINDING_TITLES[severity]),
                "discovered_date": discovered,
                "due_date": due,
                "status": status,
                "remediated_date": remediated_date,
            }
        )
    # Planted overdue findings: 6 open findings due Nov 13 — after any
    # discovered date (latest Nov 10) but before the Nov 18 as-of date.
    for finding in findings[20:26]:
        finding["due_date"] = datetime(2026, 11, 13, 0, 0, 0)
        finding["status"] = "open"
        finding["remediated_date"] = None
    # Planted invalid dates: due before discovered (discovered date is
    # pushed past the as-of date so this row is invalid but not overdue).
    findings[58]["discovered_date"] = datetime(2026, 11, 25, 0, 0, 0)
    findings[58]["due_date"] = datetime(2026, 11, 22, 0, 0, 0)
    # Planted unknown asset reference.
    findings[59]["asset_id"] = "asset-998"
    return findings


def generate_all(seed: int = SEED) -> dict:
    rng = random.Random(seed)
    identities = generate_identities(rng)
    assets = generate_assets(rng, identities)
    return {
        "identities": identities,
        "assets": assets,
        "login_events": generate_login_events(rng, identities),
        "audit_events": generate_audit_events(rng, identities, assets),
        "findings": generate_findings(rng, assets),
    }
