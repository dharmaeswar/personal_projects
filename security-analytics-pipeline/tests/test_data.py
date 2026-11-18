"""Tests for synthetic data generation: counts and planted violations."""

from security_analytics.data import AS_OF, generate_all


def test_generation_counts():
    data = generate_all()
    assert len(data["identities"]) == 40
    assert len(data["assets"]) == 30
    assert len(data["login_events"]) == 316
    assert len(data["audit_events"]) == 153
    assert len(data["findings"]) == 60


def test_generation_is_deterministic():
    assert generate_all() == generate_all()


def test_privileged_mfa_planted():
    data = generate_all()
    privileged = [i for i in data["identities"] if i["privileged"]]
    assert len(privileged) == 8
    assert sum(1 for i in privileged if i["mfa_enabled"]) == 6
    dormant = [i for i in privileged if i["last_login_days_ago"] > 90]
    assert {i["identity_id"] for i in dormant} == {"id-001", "id-021"}


def test_planted_login_violations():
    data = generate_all()
    logins = data["login_events"]
    ids = [e["event_id"] for e in logins]
    assert len(ids) - len(set(ids)) == 2  # duplicate event_ids
    assert sum(1 for e in logins if e["identity_id"] is None) == 2
    known = {i["identity_id"] for i in data["identities"]}
    assert sum(1 for e in logins if e["identity_id"] and e["identity_id"] not in known) == 2
    from security_analytics.data import WATERMARK

    assert sum(1 for e in logins if e["ts"] < WATERMARK) == 2


def test_planted_finding_violations():
    data = generate_all()
    findings = data["findings"]
    overdue = [
        f for f in findings if f["status"] == "open" and f["due_date"] < AS_OF
    ]
    assert len(overdue) == 6
    assert sum(1 for f in findings if f["due_date"] < f["discovered_date"]) == 1
    known_assets = {a["asset_id"] for a in data["assets"]}
    assert sum(1 for f in findings if f["asset_id"] not in known_assets) == 1
    assert sum(1 for f in findings if f["status"] == "remediated") == 20
    assert sum(1 for f in findings if f["status"] == "open") == 40
