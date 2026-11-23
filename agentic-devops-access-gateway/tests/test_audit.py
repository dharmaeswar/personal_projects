import pytest

from gateway import AuditLog


@pytest.fixture
def log():
    return AuditLog()


def test_record_assigns_sequence_numbers(log):
    e1 = log.record("a1", "deploy", "service:x", "srv-1", "allowed", "ok")
    e2 = log.record("a1", "delete", "service:x", "srv-1", "denied", "no scope")
    assert (e1.seq, e2.seq) == (1, 2)


def test_entries_are_immutable_and_complete(log):
    e = log.record("a1", "read", "service:x", "srv-1", "allowed", "ok")
    assert e.actor == "a1" and e.decision == "allowed" and e.reason == "ok"
    with pytest.raises(AttributeError):
        e.decision = "denied"


def test_denials_filter(log):
    log.record("a1", "read", "service:x", "srv-1", "allowed", "ok")
    log.record("a2", "delete", "service:x", "srv-1", "denied", "no scope")
    assert len(log.denials()) == 1
    assert log.denials()[0].actor == "a2"


def test_for_actor_filter(log):
    log.record("a1", "read", "service:x", "srv-1", "allowed", "ok")
    log.record("a2", "read", "service:x", "srv-1", "allowed", "ok")
    log.record("a1", "read", "service:y", "srv-1", "allowed", "ok")
    assert len(log.for_actor("a1")) == 2
    assert len(log) == 3
