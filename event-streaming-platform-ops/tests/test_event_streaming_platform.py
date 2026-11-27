"""Tests for the event-streaming platform (local simulation only)."""

import os

import pytest

from messaging import (BrokerCluster, EventBus, Queue, Rule,
                       capacity_report, check_acls, check_ansible_playbook,
                       check_chef_recipe, check_tls_config, dr_readiness,
                       evaluate_alerts, health_snapshot, load_yaml_manifest,
                       match_pattern, patch_readiness_report, restore_az,
                       simulate_az_failure, topic_exchange_match,
                       triage_findings, validate_patch_plan,
                       validate_platform_manifest)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _cluster():
    zones = {"broker-1": "us-east-1a", "broker-2": "us-east-1b",
             "broker-3": "us-east-1c"}
    cluster = BrokerCluster(list(zones), zones)
    cluster.create_topic("orders", partitions=6, replication_factor=3)
    cluster.create_topic("events", partitions=3, replication_factor=3)
    return cluster


# --- brokers ---

def test_create_topic_replicates_across_brokers():
    cluster = _cluster()
    topic = cluster.topics["orders"]
    assert len(topic.partitions) == 6
    for part in topic.partitions:
        assert len(part.replicas) == 3
        assert len(set(part.replicas)) == 3


def test_create_duplicate_topic_rejected():
    cluster = _cluster()
    with pytest.raises(ValueError):
        cluster.create_topic("orders", partitions=2)


def test_replication_factor_above_broker_count_rejected():
    cluster = _cluster()
    with pytest.raises(ValueError):
        cluster.create_topic("big", partitions=1, replication_factor=4)


def test_produce_and_consume_round_trip():
    cluster = _cluster()
    cluster.produce("orders", key="order-1", value="payload")
    records = cluster.consume("orders", "svc", max_records=10)
    assert len(records) == 1
    assert records[0].key == "order-1"
    assert cluster.total_lag("orders", "svc") == 0


def test_lag_tracks_unconsumed_records():
    cluster = _cluster()
    for i in range(20):
        cluster.produce("orders", key=f"k{i}", value="v")
    assert cluster.total_lag("orders", "svc") == 20
    consumed = cluster.consume("orders", "svc", max_records=2)
    # Consumption takes at most 2 records per partition; lag is exactly
    # what was produced minus what was consumed.
    assert cluster.total_lag("orders", "svc") == 20 - len(consumed)
    assert 0 < len(consumed) <= 12


def test_produce_fails_when_partition_leader_down():
    cluster = _cluster()
    topic = cluster.topics["orders"]
    leader = topic.partitions[0].leader
    cluster.mark_down(leader)
    with pytest.raises(RuntimeError):
        # Force the key onto partition 0 by producing until the leader
        # is hit; simpler: mark all leaders down is overkill, so find
        # a key hashing to partition 0.
        for i in range(200):
            key = f"probe-{i}"
            if topic.partition_for(key).index == 0:
                cluster.produce("orders", key=key, value="v")
                break
        else:
            raise AssertionError("no key hashed to partition 0")


def test_under_replicated_after_broker_down():
    cluster = _cluster()
    assert cluster.under_replicated_partitions() == []
    cluster.mark_down("broker-1")
    assert len(cluster.under_replicated_partitions()) > 0


def test_unknown_broker_rejected():
    cluster = _cluster()
    with pytest.raises(ValueError):
        cluster.mark_down("broker-9")


# --- routing ---

def test_pattern_match_exact_and_list():
    assert match_pattern({"source": "a", "n": 1},
                         {"source": ["a", "b"]})
    assert not match_pattern({"source": "c"}, {"source": ["a", "b"]})
    assert not match_pattern({"source": "a"}, {"source": ["a"], "n": [1]})


def test_pattern_match_nested():
    event = {"detail": {"type": "OrderPlaced", "total": 600}}
    assert match_pattern(event, {"detail": {"type": ["OrderPlaced"]}})
    assert not match_pattern(event, {"detail": {"type": ["Shipped"]}})


def test_event_bus_fanout_to_matching_queues_only():
    bus = EventBus()
    bus.add_queue(Queue("q-orders"))
    bus.add_queue(Queue("q-alerts"))
    bus.add_rule(Rule("orders", {"detail-type": ["OrderPlaced"]},
                      ["q-orders"]))
    bus.add_rule(Rule("alerts", {"detail-type": ["StockLow"]},
                      ["q-alerts"]))
    delivered = bus.publish({"detail-type": "OrderPlaced"})
    assert delivered == {"q-orders": 1}
    assert len(bus.queues["q-orders"].messages) == 1
    assert len(bus.queues["q-alerts"].messages) == 0


def test_rule_targeting_unknown_queue_rejected():
    bus = EventBus()
    with pytest.raises(ValueError):
        bus.add_rule(Rule("bad", {}, ["missing-queue"]))


def test_dlq_redrive_after_max_receives():
    dlq = Queue("dlq")
    queue = Queue("main", dead_letter=dlq, max_receives=3)
    queue.send({"id": 1})
    queue.receive(1)
    queue.receive(1)
    queue.receive(1)
    assert queue.redrive() == 1
    assert len(queue.messages) == 0
    assert len(dlq.messages) == 1


def test_no_redrive_before_max_receives():
    dlq = Queue("dlq")
    queue = Queue("main", dead_letter=dlq, max_receives=3)
    queue.send({"id": 1})
    queue.receive(1)
    assert queue.redrive() == 0
    assert len(dlq.messages) == 0


def test_topic_exchange_wildcards():
    assert topic_exchange_match("orders.us.created", "orders.*.created")
    assert topic_exchange_match("orders.us.created", "orders.#")
    assert topic_exchange_match("orders.created", "orders.#")
    assert not topic_exchange_match("orders.us.created", "orders.*.shipped")
    assert not topic_exchange_match("orders.us.created.eu",
                                    "orders.*.created")


# --- IaC ---

def test_platform_manifest_valid():
    manifest = load_yaml_manifest(os.path.join(ROOT, "iac", "platform.yaml"))
    assert validate_platform_manifest(manifest) == []


def test_manifest_rejects_low_replication():
    manifest = {"cluster": {"brokers": [
        {"id": "b1", "availability_zone": "a"},
        {"id": "b2", "availability_zone": "b"},
        {"id": "b3", "availability_zone": "c"}]},
        "topics": [{"name": "t", "partitions": 1,
                    "replication_factor": 1, "retention_hours": 168,
                    "availability_zones": ["a", "b", "c"],
                    "encryption_at_rest": True}],
        "queues": []}
    errors = validate_platform_manifest(manifest)
    assert any("replication_factor" in e for e in errors)


def test_manifest_rejects_missing_dlq():
    manifest = {"cluster": {"brokers": [
        {"id": "b1", "availability_zone": "a"},
        {"id": "b2", "availability_zone": "b"},
        {"id": "b3", "availability_zone": "c"}]},
        "topics": [],
        "queues": [{"name": "q", "visibility_timeout_seconds": 60,
                    "encryption_at_rest": True}]}
    errors = validate_platform_manifest(manifest)
    assert any("dead_letter_queue" in e for e in errors)


def test_ansible_playbook_checks_pass():
    assert check_ansible_playbook(
        os.path.join(ROOT, "iac", "ansible", "playbook.yml")) == []


def test_chef_recipe_checks_pass():
    assert check_chef_recipe(
        os.path.join(ROOT, "iac", "chef", "recipe.rb")) == []


# --- health ---

def test_health_snapshot_clean_cluster():
    cluster = _cluster()
    bus = EventBus()
    snapshot = health_snapshot(cluster, bus, {})
    assert snapshot["brokers_down"] == []
    assert snapshot["under_replicated_partitions"] == []
    assert snapshot["leaderless_partitions"] == []


def test_alerts_fire_for_down_broker_and_lag():
    cluster = _cluster()
    for i in range(20):
        cluster.produce("orders", key=f"k{i}", value="v")
    cluster.mark_down("broker-1")
    bus = EventBus()
    snapshot = health_snapshot(cluster, bus, {"svc": "orders"})
    alerts = evaluate_alerts(snapshot, lag_warn=5, lag_critical=100)
    rules = {a["rule"] for a in alerts}
    assert "broker_down" in rules
    assert "consumer_lag" in rules
    assert "under_replicated_partition" in rules


def test_alerts_fire_for_dlq_depth():
    cluster = _cluster()
    bus = EventBus()
    dlq = Queue("dlq")
    bus.add_queue(dlq)
    bus.add_queue(Queue("main", dead_letter=dlq))
    dlq.send({"id": 1})
    snapshot = health_snapshot(cluster, bus, {})
    alerts = evaluate_alerts(snapshot)
    assert any(a["rule"] == "dead_letter" for a in alerts)


def test_capacity_report_counts_records():
    cluster = _cluster()
    for i in range(9):
        cluster.produce("orders", key=f"k{i}", value="v")
    report = capacity_report(cluster)
    assert report["orders"]["records"] == 9
    assert report["orders"]["partitions"] == 6


# --- DR ---

def test_dr_readiness_ok():
    cluster = _cluster()
    readiness = dr_readiness(cluster)
    assert readiness["ready"] is True
    assert readiness["availability_zones"] == 3


def test_az_failure_promotes_replicas_and_stays_available():
    cluster = _cluster()
    result = simulate_az_failure(cluster, "us-east-1a")
    assert result["available"] is True
    assert result["lost_partitions"] == []
    assert len(result["promoted_partitions"]) > 0
    assert result["estimated_rto_minutes"] == 5
    assert cluster.leaderless_partitions() == []


def test_az_restore_brings_brokers_back():
    cluster = _cluster()
    simulate_az_failure(cluster, "us-east-1a")
    assert len(cluster.down) == 1
    restored = restore_az(cluster, "us-east-1a")
    assert restored == ["broker-1"]
    assert cluster.down == set()


# --- middleware security ---

def _good_plan():
    return {"component": "kafka", "current_version": "3.7.0",
            "target_version": "3.7.1", "cves": ["CVE-2026-1001"],
            "pre_patch_checks": ["health_snapshot"],
            "post_patch_checks": ["regression_suite"],
            "nonprod_validated": True, "rollback_plan": True}


def _good_tls():
    return {"tls_min_version": "1.2",
            "cipher": "TLS_AES_256_GCM_SHA384",
            "cert_expires_in_days": 90, "mutual_tls": True,
            "encryption_at_rest": True}


def test_triage_sorts_open_critical_high_first():
    findings = [
        {"cve": "CVE-1", "severity": "medium", "component": "kafka",
         "status": "open"},
        {"cve": "CVE-2", "severity": "critical", "component": "kafka",
         "status": "open"},
        {"cve": "CVE-3", "severity": "high", "component": "kafka",
         "status": "fixed"},
    ]
    triaged = triage_findings(findings)
    assert triaged["total_open"] == 2
    assert triaged["by_severity"] == {"medium": 1, "critical": 1}
    assert [f["cve"] for f in triaged["open_critical_high"]] == ["CVE-2"]


def test_triage_unknown_severity_rejected():
    with pytest.raises(ValueError):
        triage_findings([{"cve": "CVE-9", "severity": "urgent",
                          "component": "kafka", "status": "open"}])


def test_patch_plan_ready_when_complete():
    assert validate_patch_plan(_good_plan()) == []


def test_patch_plan_blocked_without_nonprod_validation_or_rollback():
    plan = _good_plan()
    plan["nonprod_validated"] = False
    plan["rollback_plan"] = False
    blockers = validate_patch_plan(plan)
    assert any("non-production" in b for b in blockers)
    assert any("rollback" in b for b in blockers)


def test_patch_plan_blocked_when_versions_match_or_no_cves():
    plan = _good_plan()
    plan["target_version"] = "3.7.0"
    plan["cves"] = []
    blockers = validate_patch_plan(plan)
    assert len(blockers) == 2


def test_tls_config_clean_when_hardened():
    assert check_tls_config(_good_tls()) == []


def test_tls_config_flags_old_version_and_weak_cipher():
    config = _good_tls()
    config["tls_min_version"] = "1.0"
    config["cipher"] = "RC4-SHA"
    findings = check_tls_config(config)
    rules = {f["rule"]: f["severity"] for f in findings}
    assert rules["tls_version"] == "critical"
    assert rules["weak_cipher"] == "high"


def test_tls_config_flags_expiring_cert_and_missing_mtls():
    config = _good_tls()
    config["cert_expires_in_days"] = 10
    config["mutual_tls"] = False
    findings = check_tls_config(config)
    rules = {f["rule"]: f["severity"] for f in findings}
    assert rules["cert_expiry"] == "high"
    assert rules["mutual_tls"] == "medium"


def test_acls_flag_wildcard_write_and_unknown_principal():
    acls = [{"principal": "billing-service", "resource": "*",
             "permission": "write"},
            {"principal": "ghost-service", "resource": "orders",
             "permission": "read"}]
    violations = check_acls(acls, {"billing-service"})
    rules = {v["rule"]: v["severity"] for v in violations}
    assert rules["wildcard_write"] == "critical"
    assert rules["unknown_principal"] == "high"


def test_patch_readiness_ready_only_when_all_clear():
    findings = [{"cve": "CVE-1", "severity": "high", "component": "kafka",
                 "status": "fixed"}]
    report = patch_readiness_report(
        _good_plan(), findings, _good_tls(),
        [{"principal": "svc", "resource": "orders",
          "permission": "read"}], {"svc"})
    assert report["ready"] is True
    report_blocked = patch_readiness_report(
        _good_plan(),
        [{"cve": "CVE-1", "severity": "high", "component": "kafka",
          "status": "open"}],
        _good_tls(),
        [{"principal": "svc", "resource": "orders",
          "permission": "read"}], {"svc"})
    assert report_blocked["ready"] is False
    assert len(report_blocked["open_critical_high"]) == 1
