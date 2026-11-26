"""HTTP API for the scheduling service (Python standard library only).

Endpoints:
  POST /v1/appointments                 schedule (Idempotency-Key header)
  POST /v1/appointments/{id}/reschedule
  POST /v1/appointments/{id}/assign
  POST /v1/appointments/{id}/cancel
  POST /v1/appointments/{id}/complete
  GET  /v1/technicians/{id}/schedule?date=YYYY-MM-DD
  GET  /v1/customers/{id}/appointments
  GET  /health

Run: python3 run_demo.py  (also exercises the service end to end)
     python3 -m scheduling.api  (serves on :8080)
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .commands import SchedulingService
from .events import EventStore
from .projections import CustomerAppointmentsProjection


def build_service(store_path: str | None = None):
    store = EventStore(store_path)
    service = SchedulingService(store)
    customers = CustomerAppointmentsProjection()
    customers.rebuild(store.all_events())
    return store, service, customers


class Handler(BaseHTTPRequestHandler):
    store, service, customers = build_service(
        os.environ.get("SCHEDULING_STORE"))

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length) or b"{}")

    def log_message(self, *args):  # keep stdout clean
        pass

    def do_POST(self):  # noqa: N802
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        body = self._body()
        try:
            if parts == ["v1", "appointments"]:
                key = self.headers.get("Idempotency-Key")
                event, created = self.service.schedule_appointment(
                    body["customer_id"], body["technician_id"],
                    body["service_type"], body["start"],
                    int(body["duration_min"]), idempotency_key=key)
                self.customers.rebuild(self.store.all_events())
                self._send(201 if created else 200,
                           {"appointment_id": event.aggregate_id,
                            "event": event.event_type,
                            "created": created})
            elif len(parts) == 4 and parts[:2] == ["v1", "appointments"]:
                appt_id, action = parts[2], parts[3]
                if action == "reschedule":
                    event, _ = self.service.reschedule(
                        appt_id, body["start"], int(body["duration_min"]),
                        idempotency_key=self.headers.get("Idempotency-Key"))
                elif action == "assign":
                    event = self.service.assign_technician(
                        appt_id, body["technician_id"])
                elif action == "cancel":
                    event = self.service.cancel(appt_id, body.get("reason", ""))
                elif action == "complete":
                    event = self.service.complete(appt_id)
                else:
                    return self._send(404, {"error": "unknown action"})
                self.customers.rebuild(self.store.all_events())
                self._send(200, {"appointment_id": appt_id,
                                 "event": event.event_type})
            else:
                self._send(404, {"error": "unknown route"})
        except (KeyError, ValueError) as exc:
            self._send(400, {"error": str(exc)})

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        if parts == ["health"]:
            return self._send(200, {"status": "ok"})
        if len(parts) == 4 and parts[:2] == ["v1", "technicians"] \
                and parts[3] == "schedule":
            date = parse_qs(parsed.query).get("date", [""])[0]
            return self._send(200, {"technician_id": parts[2], "date": date,
                                    "slots": self.service.schedule.day_schedule(
                                        parts[2], date)})
        if len(parts) == 4 and parts[:2] == ["v1", "customers"] \
                and parts[3] == "appointments":
            return self._send(200, {"customer_id": parts[2],
                                    "appointments": self.customers.appointments_for(parts[2])})
        self._send(404, {"error": "unknown route"})


def main(port: int = 8080) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"in-home scheduling API on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main(int(os.environ.get("PORT", "8080")))
