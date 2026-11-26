import json
import threading
import urllib.request

import pytest

from scheduling.api import Handler, ThreadingHTTPServer


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _req(base, method, path, body=None, headers=None):
    req = urllib.request.Request(
        base + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_health_and_full_flow(server):
    status, body = _req(server, "GET", "/health")
    assert status == 200 and body["status"] == "ok"

    status, body = _req(server, "POST", "/v1/appointments", {
        "customer_id": "cust-9", "technician_id": "tech-9",
        "service_type": "repair", "start": "2026-12-03T10:00:00",
        "duration_min": 90}, headers={"Idempotency-Key": "api-key-1"})
    assert status == 201
    appt_id = body["appointment_id"]

    # Same idempotency key: no duplicate booking.
    status, body2 = _req(server, "POST", "/v1/appointments", {
        "customer_id": "cust-9", "technician_id": "tech-9",
        "service_type": "repair", "start": "2026-12-03T10:00:00",
        "duration_min": 90}, headers={"Idempotency-Key": "api-key-1"})
    assert status == 200 and body2["appointment_id"] == appt_id

    status, body = _req(server, "GET",
                        "/v1/technicians/tech-9/schedule?date=2026-12-03")
    assert status == 200 and len(body["slots"]) == 1

    status, body = _req(server, "GET", "/v1/customers/cust-9/appointments")
    assert status == 200 and len(body["appointments"]) == 1

    status, body = _req(server, "POST",
                        f"/v1/appointments/{appt_id}/complete", {})
    assert status == 200 and body["event"] == "AppointmentCompleted"

    # A completed slot is free again: the same technician/time can be booked.
    status, body = _req(server, "POST", "/v1/appointments", {
        "customer_id": "cust-9", "technician_id": "tech-9",
        "service_type": "delivery", "start": "2026-12-03T10:00:00",
        "duration_min": 30})
    assert status == 201
