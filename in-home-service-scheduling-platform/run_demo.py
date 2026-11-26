"""End-to-end demo: book, dispatch, reschedule, complete — all through
the event-sourced service, then show the read models rebuilt by replay.
"""
from scheduling.commands import SchedulingService
from scheduling.dispatch import PartnerDispatchClient, record_dispatch
from scheduling.events import EventStore
from scheduling.projections import (
    CustomerAppointmentsProjection, TechnicianScheduleProjection)


def main() -> None:
    store = EventStore()
    service = SchedulingService(store)

    event, _ = service.schedule_appointment(
        "cust-100", "tech-7", "installation", "2026-12-04T09:00:00", 120,
        idempotency_key="demo-1", appointment_id="demo-appt-1")
    print(f"scheduled {event.aggregate_id} 09:00-11:00 installation")

    # Partner dispatch with one transient failure, then success.
    attempts = {"n": 0}

    def send(appt_id, payload):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ConnectionError("partner timeout")
        return {"confirmation": "P-9001"}

    client = PartnerDispatchClient(send)
    result = client.dispatch("demo-appt-1", {"technician_id": "tech-7"})
    record_dispatch(store, "demo-appt-1", "dispatched", result["attempts"])
    print(f"partner dispatch confirmed {result['partner_response']} "
          f"after {result['attempts']} attempts")

    service.reschedule("demo-appt-1", "2026-12-04T13:00:00", 120)
    service.complete("demo-appt-1")
    print(f"rescheduled to 13:00, then completed; "
          f"{len(store.all_events())} events in the store")

    # Read models rebuilt purely by replaying the event stream.
    tech = TechnicianScheduleProjection()
    tech.rebuild(store.all_events())
    print("tech-7 on 2026-12-04:",
          tech.day_schedule("tech-7", "2026-12-04"))
    customers = CustomerAppointmentsProjection()
    customers.rebuild(store.all_events())
    print("cust-100 appointments:", customers.appointments_for("cust-100"))


if __name__ == "__main__":
    main()
