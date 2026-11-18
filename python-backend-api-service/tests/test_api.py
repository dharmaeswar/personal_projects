"""Integration tests: real HTTP requests against a live server thread."""

import http.client
import json
import threading

import pytest

from payments_api.app import create_server


@pytest.fixture(scope="module")
def server():
    srv = create_server(port=0)  # OS picks a free port
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def _request(server, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    payload = json.dumps(body) if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    conn.request(method, path, body=payload, headers=hdrs)
    resp = conn.getresponse()
    data = json.loads(resp.read().decode() or "{}")
    conn.close()
    return resp.status, data


def test_health(server):
    status, data = _request(server, "GET", "/health")
    assert status == 200
    assert data == {"status": "ok"}


def test_checkout_creates_loan_with_schedule(server):
    status, data = _request(
        server,
        "POST",
        "/v1/checkout",
        {
            "principal_cents": 120_000,
            "apr_bps": 1500,
            "term_months": 12,
            "merchant_id": "merchant_1",
            "customer_id": "cust_42",
        },
    )
    assert status == 201
    assert data["total_due_cents"] == 129_972
    assert data["status"] == "active"
    loan_id = data["id"]

    status, schedule = _request(server, "GET", f"/v1/loans/{loan_id}/schedule")
    assert status == 200
    assert len(schedule["schedule"]) == 12
    assert schedule["schedule"][-1]["remaining_balance_cents"] == 0


def test_checkout_validation_error_returns_400(server):
    status, data = _request(
        server,
        "POST",
        "/v1/checkout",
        {"principal_cents": -5, "apr_bps": 1500, "term_months": 12,
         "merchant_id": "m1", "customer_id": "c1"},
    )
    assert status == 400
    assert "principal_cents" in data["error"]


def test_idempotent_checkout_returns_same_loan(server):
    headers = {"Idempotency-Key": "checkout-abc-123"}
    body = {
        "principal_cents": 60_000,
        "apr_bps": 0,
        "term_months": 6,
        "merchant_id": "merchant_2",
        "customer_id": "cust_7",
    }
    before = server.loan_store.count()
    status1, first = _request(server, "POST", "/v1/checkout", body, headers)
    status2, second = _request(server, "POST", "/v1/checkout", body, headers)
    assert status1 == 201
    assert status2 == 200
    assert first["id"] == second["id"]
    assert server.loan_store.count() == before + 1  # no duplicate loan created


def test_payment_flow_end_to_end(server):
    _, loan = _request(
        server,
        "POST",
        "/v1/checkout",
        {"principal_cents": 30_000, "apr_bps": 0, "term_months": 3,
         "merchant_id": "m3", "customer_id": "c3"},
    )
    loan_id = loan["id"]
    status, data = _request(
        server, "POST", f"/v1/loans/{loan_id}/payments", {"amount_cents": 10_000}
    )
    assert status == 200
    assert data["paid_cents"] == 10_000
    assert data["status"] == "active"

    status, data = _request(
        server, "POST", f"/v1/loans/{loan_id}/payments", {"amount_cents": 20_000}
    )
    assert status == 200
    assert data["status"] == "paid_off"


def test_unknown_loan_returns_404(server):
    status, data = _request(server, "GET", "/v1/loans/loan_999999")
    assert status == 404
    assert data["error"] == "loan not found"


def test_unknown_route_returns_404(server):
    status, _ = _request(server, "GET", "/v1/nope")
    assert status == 404
