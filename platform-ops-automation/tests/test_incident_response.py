"""Tests for the incident-response module (on-call, lifecycle, SLA, tickets)."""
from datetime import datetime, timedelta, timezone

import pytest

from ops.incident_response import (
    RUNBOOKS, Incident, TicketStore, incident_summary, on_call)

START = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)  # a Monday
ROSTER = ["ana", "ben", "cara", "dev"]


def _incident(severity="Sev2", detected_at=None):
    return Incident("INC-1", "High error rate on teller service", severity,
                    "teller", detected_at or START)


# --- on-call rotation ---

def test_on_call_first_week():
    assert on_call(ROSTER, START, START) == {"primary": "ana", "secondary": "ben"}


def test_on_call_rotates_weekly():
    assert on_call(ROSTER, START, START + timedelta(days=7))["primary"] == "ben"
    assert on_call(ROSTER, START, START + timedelta(days=21))["primary"] == "dev"
    assert on_call(ROSTER, START, START + timedelta(days=28))["primary"] == "ana"


def test_on_call_midweek_stays_put():
    assert on_call(ROSTER, START, START + timedelta(days=3))["primary"] == "ana"
    assert on_call(ROSTER, START, START + timedelta(days=6, hours=23))["primary"] == "ana"


def test_on_call_errors():
    with pytest.raises(ValueError, match="roster is empty"):
        on_call([], START, START)
    with pytest.raises(ValueError, match="before the rotation start"):
        on_call(ROSTER, START, START - timedelta(days=1))


# --- incident lifecycle ---

def test_full_lifecycle():
    incident = _incident()
    assert incident.state == "detected"
    incident.transition("triaged", START + timedelta(minutes=10), "ana")
    assert incident.acknowledged_at == START + timedelta(minutes=10)
    incident.transition("mitigating", START + timedelta(minutes=30), "ana")
    incident.transition("resolved", START + timedelta(hours=2), "ben")
    assert incident.resolved_at == START + timedelta(hours=2)
    incident.transition("closed", START + timedelta(hours=3), "ana")
    assert incident.state == "closed"
    assert len(incident.history) == 5


def test_invalid_transitions_rejected():
    incident = _incident()
    with pytest.raises(ValueError, match="Cannot move"):
        incident.transition("resolved", START, "ana")  # detected -> resolved
    incident.transition("triaged", START, "ana")
    with pytest.raises(ValueError, match="Cannot move"):
        incident.transition("closed", START, "ana")  # triaged -> closed
    with pytest.raises(ValueError, match="before the incident was detected"):
        incident.transition("mitigating", START - timedelta(hours=1), "ana")


def test_unknown_severity_and_runbook_rejected():
    with pytest.raises(ValueError, match="Unknown severity"):
        _incident(severity="Sev9")
    with pytest.raises(ValueError, match="Unknown runbook"):
        Incident("INC-2", "x", "Sev2", "teller", START, runbook="nope")


def test_runbook_steps():
    incident = _incident()
    steps = incident.runbook_steps()
    assert steps == RUNBOOKS["high-error-rate"]
    assert len(steps) == 3


# --- SLA ---

def test_sla_met_when_acknowledged_and_resolved_on_time():
    incident = _incident(severity="Sev1")
    incident.transition("triaged", START + timedelta(minutes=10), "ana")
    incident.transition("resolved", START + timedelta(hours=3), "ana")
    sla = incident.sla_status(START + timedelta(hours=3))
    assert sla["acknowledge_breached"] is False
    assert sla["resolve_breached"] is False


def test_sla_acknowledge_breach():
    incident = _incident(severity="Sev1")
    sla = incident.sla_status(START + timedelta(minutes=16))
    assert sla["acknowledge_breached"] is True
    assert sla["resolve_breached"] is False


def test_sla_resolve_breach_after_deadline():
    incident = _incident(severity="Sev2")
    incident.transition("triaged", START + timedelta(minutes=30), "ana")
    sla = incident.sla_status(START + timedelta(hours=25))
    assert sla["acknowledge_breached"] is False
    assert sla["resolve_breached"] is True


# --- tickets ---

def test_ticket_create_sync_close():
    incident = _incident()
    store = TicketStore()
    ticket = store.create_from_incident(incident, "platform-sre")
    assert ticket["number"] == "INC-1000"
    assert ticket["state"] == "new"
    incident.transition("triaged", START + timedelta(minutes=10), "ana")
    assert store.sync(incident, "INC-1000")["state"] == "in_progress"
    incident.transition("mitigating", START + timedelta(minutes=30), "ana")
    incident.transition("resolved", START + timedelta(hours=2), "ben")
    assert store.sync(incident, "INC-1000")["state"] == "resolved"
    incident.transition("closed", START + timedelta(hours=3), "ana")
    assert store.sync(incident, "INC-1000")["state"] == "closed"


def test_ticket_sync_errors():
    incident = _incident()
    other = Incident("INC-2", "Latency spike", "Sev3", "teller", START)
    store = TicketStore()
    store.create_from_incident(incident, "platform-sre")
    with pytest.raises(KeyError, match="Unknown ticket"):
        store.sync(incident, "INC-9999")
    with pytest.raises(ValueError, match="belongs to incident"):
        store.sync(other, "INC-1000")


def test_ticket_numbers_increment():
    store = TicketStore()
    first = store.create_from_incident(_incident(), "platform-sre")
    second = store.create_from_incident(
        Incident("INC-2", "x", "Sev3", "teller", START), "platform-sre")
    assert first["number"] == "INC-1000"
    assert second["number"] == "INC-1001"


# --- fleet summary ---

def test_incident_summary_counts_and_breaches():
    on_time = _incident(severity="Sev3")
    on_time.transition("triaged", START + timedelta(minutes=30), "ana")
    breached = _incident(severity="Sev1")
    breached.detected_at = START
    summary = incident_summary([on_time, breached], START + timedelta(hours=1))
    assert summary["total"] == 2
    assert summary["by_state"] == {"triaged": 1, "detected": 1}
    assert summary["by_severity"] == {"Sev3": 1, "Sev1": 1}
    assert summary["sla_breached"] == 1  # the unacknowledged Sev1
