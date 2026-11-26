"""CQRS read models, rebuilt by replaying the event stream.

Write side: commands append events (commands.py). Read side: these
projections fold the same events into query-friendly views. A projection
can always be rebuilt from scratch by replaying the store, so the read
models never need their own write path.
"""
from __future__ import annotations

from datetime import datetime

from .events import Event


def _overlaps(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    return a_start < b_end and b_start < a_end


class TechnicianScheduleProjection:
    """Per-technician, per-day list of booked slots (the scheduling view)."""

    def __init__(self):
        # (technician_id, date) -> list of {appointment_id, start, end, status}
        self.slots: dict[tuple[str, str], list[dict]] = {}

    def _find_slot(self, appointment_id: str):
        for key, entries in self.slots.items():
            for entry in entries:
                if entry["appointment_id"] == appointment_id:
                    return key, entry
        return None, None

    def apply(self, event: Event) -> None:
        p = event.payload
        if event.event_type == "AppointmentScheduled":
            key = (p["technician_id"], p["start"][:10])
            self.slots.setdefault(key, []).append({
                "appointment_id": event.aggregate_id,
                "start": p["start"], "end": p["end"],
                "status": "scheduled",
            })
        elif event.event_type == "AppointmentRescheduled":
            key, entry = self._find_slot(event.aggregate_id)
            if entry is not None:
                entry["start"], entry["end"] = p["start"], p["end"]
                new_key = (key[0], p["start"][:10])
                if new_key != key:
                    self.slots[key].remove(entry)
                    self.slots.setdefault(new_key, []).append(entry)
        elif event.event_type == "TechnicianAssigned":
            key, entry = self._find_slot(event.aggregate_id)
            if entry is not None:
                new_key = (p["technician_id"], entry["start"][:10])
                if new_key != key:
                    self.slots[key].remove(entry)
                    self.slots.setdefault(new_key, []).append(entry)
        elif event.event_type in ("AppointmentCancelled", "AppointmentCompleted"):
            _, entry = self._find_slot(event.aggregate_id)
            if entry is not None:
                entry["status"] = (
                    "cancelled" if event.event_type == "AppointmentCancelled"
                    else "completed")

    def rebuild(self, events: list[Event]) -> None:
        self.slots = {}
        for event in events:
            self.apply(event)

    def is_free(self, technician_id: str, start: str, end: str) -> bool:
        for entry in self.slots.get((technician_id, start[:10]), []):
            if entry["status"] in ("scheduled",) and _overlaps(
                    start, end, entry["start"], entry["end"]):
                return False
        return True

    def day_schedule(self, technician_id: str, date: str) -> list[dict]:
        return sorted(self.slots.get((technician_id, date), []),
                      key=lambda e: e["start"])


class CustomerAppointmentsProjection:
    """Per-customer appointment list (the customer-facing view)."""

    def __init__(self):
        self.by_customer: dict[str, list[dict]] = {}

    def apply(self, event: Event) -> None:
        p = event.payload
        if event.event_type == "AppointmentScheduled":
            self.by_customer.setdefault(p["customer_id"], []).append({
                "appointment_id": event.aggregate_id,
                "service_type": p["service_type"],
                "technician_id": p["technician_id"],
                "start": p["start"], "end": p["end"],
                "status": "scheduled",
            })
        elif event.event_type == "AppointmentRescheduled":
            for appts in self.by_customer.values():
                for appt in appts:
                    if appt["appointment_id"] == event.aggregate_id:
                        appt["start"], appt["end"] = p["start"], p["end"]
        elif event.event_type == "TechnicianAssigned":
            for appts in self.by_customer.values():
                for appt in appts:
                    if appt["appointment_id"] == event.aggregate_id:
                        appt["technician_id"] = p["technician_id"]
        elif event.event_type in ("AppointmentCancelled", "AppointmentCompleted"):
            for appts in self.by_customer.values():
                for appt in appts:
                    if appt["appointment_id"] == event.aggregate_id:
                        appt["status"] = (
                            "cancelled" if event.event_type == "AppointmentCancelled"
                            else "completed")

    def rebuild(self, events: list[Event]) -> None:
        self.by_customer = {}
        for event in events:
            self.apply(event)

    def appointments_for(self, customer_id: str) -> list[dict]:
        return sorted(self.by_customer.get(customer_id, []),
                      key=lambda a: a["start"])
