import pytest

from scheduling.commands import SchedulingService
from scheduling.events import EventStore
from scheduling.projections import (
    CustomerAppointmentsProjection, TechnicianScheduleProjection)


@pytest.fixture
def service():
    return SchedulingService(EventStore())


def _book(service, tech="tech-1", start="2026-12-01T09:00:00", key=None,
          appt="appt-1"):
    return service.schedule_appointment(
        "cust-1", tech, "installation", start, 120,
        idempotency_key=key, appointment_id=appt)


def test_schedule_and_replay_rebuilds_state(service):
    event, created = _book(service)
    assert created and event.event_type == "AppointmentScheduled"
    assert event.version == 1
    state = service.appointment("appt-1")
    assert state["status"] == "scheduled"
    assert state["end"] == "2026-12-01T11:00:00"
    # State is derived from events only: rebuild from the store.
    replayed = SchedulingService(EventStore())
    replayed.store._events = list(service.store.all_events())
    replayed.schedule.rebuild(replayed.store.all_events())
    assert replayed.appointment("appt-1")["status"] == "scheduled"


def test_double_booking_same_technician_rejected(service):
    _book(service)
    with pytest.raises(ValueError, match="already booked"):
        _book(service, start="2026-12-01T10:00:00", appt="appt-2")
    # Adjacent slot is fine; a different technician is fine.
    _book(service, start="2026-12-01T11:00:00", appt="appt-2")
    _book(service, tech="tech-2", start="2026-12-01T10:00:00", appt="appt-3")


def test_idempotent_replay_writes_no_duplicate_event(service):
    event, created = _book(service, key="key-1")
    again, created_again = _book(service, key="key-1")
    assert created and not created_again
    assert again.event_id == event.event_id
    assert len(service.store.all_events()) == 1


def test_reschedule_cancel_complete_lifecycle(service):
    _book(service)
    service.reschedule("appt-1", "2026-12-02T13:00:00", 60)
    state = service.appointment("appt-1")
    assert state["start"] == "2026-12-02T13:00:00"
    assert state["end"] == "2026-12-02T14:00:00"
    service.complete("appt-1")
    assert service.appointment("appt-1")["status"] == "completed"
    with pytest.raises(ValueError, match="cannot cancel"):
        service.cancel("appt-1")


def test_reschedule_into_booked_slot_rejected(service):
    _book(service, appt="appt-1")
    _book(service, start="2026-12-01T13:00:00", appt="appt-2")
    with pytest.raises(ValueError, match="already booked"):
        service.reschedule("appt-1", "2026-12-01T13:30:00", 60)


def test_cancel_frees_the_slot(service):
    _book(service)
    service.cancel("appt-1", reason="customer request")
    assert service.schedule.is_free("tech-1", "2026-12-01T09:00:00",
                                    "2026-12-01T11:00:00")
    _book(service, appt="appt-2")


def test_unknown_service_type_and_bad_duration(service):
    with pytest.raises(ValueError, match="unknown service_type"):
        service.schedule_appointment("c", "t", "cleaning",
                                     "2026-12-01T09:00:00", 60)
    with pytest.raises(ValueError, match="positive"):
        service.schedule_appointment("c", "t", "repair",
                                     "2026-12-01T09:00:00", 0)


def test_version_conflict_detected():
    store = EventStore()
    service = SchedulingService(store)
    _book(service)
    from scheduling.events import new_event
    with pytest.raises(ValueError, match="version conflict"):
        store.append(new_event("appt-1", "AppointmentCancelled", 1,
                               {"reason": "x"}))


def test_projections_rebuilt_from_events(service):
    _book(service)
    service.assign_technician("appt-1", "tech-9")
    customers = CustomerAppointmentsProjection()
    customers.rebuild(service.store.all_events())
    appts = customers.appointments_for("cust-1")
    assert len(appts) == 1 and appts[0]["technician_id"] == "tech-9"
    tech = TechnicianScheduleProjection()
    tech.rebuild(service.store.all_events())
    assert len(tech.day_schedule("tech-9", "2026-12-01")) == 1
    assert tech.day_schedule("tech-1", "2026-12-01") == []
