"""Audit trail: hash chaining, tamper detection, ordering."""
import pytest

from comp_engine import AuditLog


def test_empty_log_verifies():
    assert AuditLog().verify() is True


def test_events_chain_and_verify():
    log = AuditLog()
    first = log.record("commission_calculated", "D1", "gross=8000")
    second = log.record("payment_scheduled", "PAY-1", "payable=7200")
    assert first.seq == 1
    assert second.seq == 2
    assert second.prev_hash == first.event_hash
    assert first.prev_hash == "0" * 64
    assert log.verify() is True


def test_tampered_detail_breaks_chain():
    log = AuditLog()
    log.record("commission_calculated", "D1", "gross=8000")
    log.record("payment_scheduled", "PAY-1", "payable=7200")
    log._events[0].detail = "gross=99999"
    assert log.verify() is False


def test_removed_event_breaks_chain():
    log = AuditLog()
    log.record("commission_calculated", "D1", "gross=8000")
    log.record("payment_scheduled", "PAY-1", "payable=7200")
    log.record("payment_paid", "PAY-1", "paid")
    log._events.pop(1)
    assert log.verify() is False


def test_many_events_stay_valid():
    log = AuditLog()
    for i in range(50):
        log.record("event", f"E{i}", f"detail {i}")
    assert len(log.events()) == 50
    assert log.verify() is True
