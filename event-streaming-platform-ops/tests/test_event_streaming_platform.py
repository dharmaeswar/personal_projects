"""Tests for the event-streaming platform (local simulation only)."""

import os

import pytest

from messaging import (BrokerCluster, EventBus, Queue, Rule,
                       capacity_report, check_ansible_playbook,
                       check_chef_recipe, dr_readiness, evaluate_alerts,
                       health_snapshot, load_yaml_manifest, match_pattern,
                       restore_az, simulate_az_failure,
                       topic_exchange_match, validate_platform_manifest)

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
