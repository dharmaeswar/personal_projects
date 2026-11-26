"""Command handlers — the write side of the CQRS model.

Each command validates against the current state (rebuilt by replaying
the aggregate's events), then appends exactly one event. Commands carry
an idempotency key: replaying the same command returns the original
event instead of appending a duplicate, so a retried request can never
double-book an appointment.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from .events import EventStore, new_event
from .projections import TechnicianScheduleProjection

SERVICE_TYPES = ("delivery", "installation", "repair")


def _end(start_iso: str, duration_min: int) -> str:
    start = datetime.fromisoformat(start_iso)
    return (start + timedelta(minutes=duration_min)).isoformat()


def _current_state(store: EventStore, appointment_id: str) -> dict | None:
    state: dict | None = None
    for event in store.events_for(appointment_id):
        p = event.payload
        if event.event_type == "AppointmentScheduled":
            state = {"status": "scheduled", **p}
        elif event.event_type == "AppointmentRescheduled":
            if state:
                state.update({"start": p["start"], "end": p["end"]})
        elif event.event_type == "TechnicianAssigned":
            if state:
                state["technician_id"] = p["technician_id"]
        elif event.event_type == "AppointmentCancelled":
            if state:
                state["status"] = "cancelled"
        elif event.event_type == "AppointmentCompleted":
            if state:
                state["status"] = "completed"
    return state


class SchedulingService:
    def __init__(self, store: EventStore):
        self.store = store
        self.schedule = TechnicianScheduleProjection()
        self.schedule.rebuild(store.all_events())

    def _append(self, appointment_id: str, event_type: str, payload: dict,
                idempotency_key: str | None = None):
        event = new_event(
            appointment_id, event_type,
            self.store.next_version(appointment_id),
            payload, idempotency_key)
        self.store.append(event)
        self.schedule.apply(event)
        return event

    def schedule_appointment(self, customer_id: str, technician_id: str,
                             service_type: str, start: str, duration_min: int,
                             idempotency_key: str | None = None,
                             appointment_id: str | None = None):
        if service_type not in SERVICE_TYPES:
            raise ValueError(f"unknown service_type {service_type!r}")
        if duration_min <= 0:
            raise ValueError("duration_min must be positive")
        if idempotency_key:
            prior = self.store.find_by_idempotency_key(idempotency_key)
            if prior is not None:
                return prior, False  # replayed: no new event
        end = _end(start, duration_min)
        if not self.schedule.is_free(technician_id, start, end):
            raise ValueError(
                f"technician {technician_id} already booked {start}–{end}")
        appointment_id = appointment_id or str(uuid.uuid4())
        event = self._append(appointment_id, "AppointmentScheduled", {
            "customer_id": customer_id, "technician_id": technician_id,
            "service_type": service_type, "start": start, "end": end,
            "duration_min": duration_min,
        }, idempotency_key)
        return event, True

    def reschedule(self, appointment_id: str, start: str, duration_min: int,
                   idempotency_key: str | None = None):
        state = _current_state(self.store, appointment_id)
        if state is None:
            raise ValueError(f"unknown appointment {appointment_id}")
        if state["status"] != "scheduled":
            raise ValueError(f"cannot reschedule a {state['status']} appointment")
        if idempotency_key:
            prior = self.store.find_by_idempotency_key(idempotency_key)
            if prior is not None:
                return prior, False
        end = _end(start, duration_min)
        # Temporarily ignore this appointment's own slot when checking.
        if not self.schedule.is_free(state["technician_id"], start, end):
            overlapping = [
                e for e in self.schedule.day_schedule(
                    state["technician_id"], start[:10])
                if e["appointment_id"] != appointment_id
                and e["status"] == "scheduled"
                and e["start"] < end and start < e["end"]]
            if overlapping:
                raise ValueError(
                    f"technician {state['technician_id']} already booked {start}–{end}")
        return self._append(appointment_id, "AppointmentRescheduled",
                            {"start": start, "end": end,
                             "duration_min": duration_min}, idempotency_key), True

    def assign_technician(self, appointment_id: str, technician_id: str):
        state = _current_state(self.store, appointment_id)
        if state is None:
            raise ValueError(f"unknown appointment {appointment_id}")
        if state["status"] != "scheduled":
            raise ValueError(f"cannot reassign a {state['status']} appointment")
        if not self.schedule.is_free(technician_id, state["start"], state["end"]):
            raise ValueError(
                f"technician {technician_id} already booked "
                f"{state['start']}–{state['end']}")
        return self._append(appointment_id, "TechnicianAssigned",
                            {"technician_id": technician_id})

    def cancel(self, appointment_id: str, reason: str = ""):
        state = _current_state(self.store, appointment_id)
        if state is None:
            raise ValueError(f"unknown appointment {appointment_id}")
        if state["status"] != "scheduled":
            raise ValueError(f"cannot cancel a {state['status']} appointment")
        return self._append(appointment_id, "AppointmentCancelled",
                            {"reason": reason})

    def complete(self, appointment_id: str):
        state = _current_state(self.store, appointment_id)
        if state is None:
            raise ValueError(f"unknown appointment {appointment_id}")
        if state["status"] != "scheduled":
            raise ValueError(f"cannot complete a {state['status']} appointment")
        return self._append(appointment_id, "AppointmentCompleted", {})

    def appointment(self, appointment_id: str) -> dict | None:
        return _current_state(self.store, appointment_id)
