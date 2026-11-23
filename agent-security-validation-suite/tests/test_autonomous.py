from agent_security.autonomous import (
    BruteForceDetector, EgressAnomalyDetector, IndicatorMatchDetector,
    PrivilegeEscalationDetector, Responder, Signal, detect_all,
    run_autonomous_suite)


def sig(sid, ts, source, kind, sev=2, **ind):
    return Signal(sid, ts, source, kind, sev, ind)


def test_brute_force_fires_at_threshold():
    rows = [sig(f"a{i}", 1000 + i * 10, "10.0.0.7", "auth.failure", 3)
            for i in range(5)]
    found = BruteForceDetector().detect(rows)
    assert len(found) == 1
    assert found[0].severity == 4 and found[0].confidence == 0.9
    assert "5 failed logins" in found[0].evidence


def test_brute_force_below_threshold_and_spread_out():
    rows = [sig(f"a{i}", 1000 + i * 10, "10.0.0.7", "auth.failure", 3)
            for i in range(4)]
    assert BruteForceDetector().detect(rows) == []
    spread = [sig(f"s{i}", 1000 + i * 120, "10.0.0.7", "auth.failure", 3)
              for i in range(6)]
    assert BruteForceDetector().detect(spread) == []


def test_egress_anomaly_threshold():
    big = [sig("e1", 2000, "host-9", "egress.bytes", 3, bytes=10_000_001)]
    assert len(EgressAnomalyDetector().detect(big)) == 1
    edge = [sig("e2", 2000, "host-9", "egress.bytes", 1, bytes=10_000_000)]
    assert EgressAnomalyDetector().detect(edge) == []


def test_privilege_escalation_needs_read_only_then_admin():
    chain = [
        sig("p1", 3000, "console", "role.assume", 2,
            subject="alice", role="read-only"),
        sig("p2", 3300, "console", "role.assume", 4,
            subject="alice", role="admin"),
    ]
    found = PrivilegeEscalationDetector().detect(chain)
    assert len(found) == 1 and found[0].severity == 5
    other_subject = [
        sig("p1", 3000, "console", "role.assume", 2,
            subject="alice", role="read-only"),
        sig("p2", 3300, "console", "role.assume", 4,
            subject="bob", role="admin"),
    ]
    assert PrivilegeEscalationDetector().detect(other_subject) == []
    too_late = [
        sig("p1", 3000, "console", "role.assume", 2,
            subject="alice", role="read-only"),
        sig("p2", 4000, "console", "role.assume", 4,
            subject="alice", role="admin"),
    ]
    assert PrivilegeEscalationDetector().detect(too_late) == []


def test_indicator_match_only_on_known_bad():
    det = IndicatorMatchDetector({"bad-domain.example"})
    hit = [sig("i1", 4000, "host-4", "indicator.hit", 4,
               indicators=["bad-domain.example"])]
    assert len(det.detect(hit)) == 1
    miss = [sig("i2", 4000, "host-4", "indicator.hit", 1,
                indicators=["clean.example"])]
    assert det.detect(miss) == []


def test_detect_all_sorts_by_severity():
    rows = [sig(f"a{i}", 1000 + i * 5, "10.0.0.7", "auth.failure", 3)
            for i in range(5)]
    rows.append(sig("e1", 2000, "host-9", "egress.bytes", 3,
                    bytes=12_000_000))
    found = detect_all(rows)
    assert [f.detector for f in found] == ["brute_force", "egress_anomaly"]


def test_responder_auto_actions_by_severity():
    responder = Responder()
    from agent_security.autonomous import Finding
    low = Finding("f-low", "test", 1, 0.5, "host-1", "low")
    actions = {a.action: a.status for a in responder.respond(low)}
    assert actions == {"log_finding": "executed"}
    mid = Finding("f-mid", "test", 3, 0.8, "host-1", "mid")
    actions = {a.action: a.status for a in responder.respond(mid)}
    assert actions["revoke_session"] == "executed"
    assert "disable_account" not in actions


def test_responder_holds_destructive_actions_for_approval():
    from agent_security.autonomous import Finding
    responder = Responder()
    critical = Finding("f-crit", "privilege_escalation", 5, 0.95,
                       "alice", "escalation")
    actions = {a.action: a.status for a in responder.respond(critical)}
    assert actions["disable_account"] == "pending_approval"
    assert actions["isolate_network"] == "pending_approval"
    assert actions["revoke_session"] == "executed"


def test_responder_is_idempotent_per_finding():
    from agent_security.autonomous import Finding
    responder = Responder()
    finding = Finding("f-1", "brute_force", 4, 0.9, "10.0.0.7", "burst")
    first = responder.respond(finding)
    assert all(a.status == "executed" for a in first)
    second = responder.respond(finding)
    assert all(a.status == "skipped_duplicate" for a in second)
    assert len(second) == len(first)


def test_autonomous_suite_all_pass():
    rows = run_autonomous_suite()
    assert len(rows) == 8
    failed = [r for r in rows if not r["passed"]]
    assert failed == [], failed
