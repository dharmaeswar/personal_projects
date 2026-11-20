import json
import threading

import pytest
from event_intel.api import make_handler
from event_intel.auth import TokenStore
from event_intel.store import EventStore

from http.server import ThreadingHTTPServer
from urllib import request as urlrequest
from urllib.error import HTTPError


@pytest.fixture()
def server():
    store = EventStore()
    tokens = TokenStore()
    read_token = tokens.mint_token(["alerts:read"])
    write_token = tokens.mint_token(["events:write"])
    both_token = tokens.mint_token(["alerts:read", "events:write"])
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store, tokens))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield {"base": base, "store": store, "read": read_token, "write": write_token, "both": both_token}
    httpd.shutdown()
    httpd.server_close()


def call(base, path, method="GET", token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urlrequest.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urlrequest.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def test_health_needs_no_auth(server):
    status, payload = call(server["base"], "/health")
    assert status == 200
    assert payload["status"] == "ok"


def test_list_alerts_requires_auth(server):
    status, _ = call(server["base"], "/v1/alerts")
    assert status == 401


def test_list_alerts_rejects_write_only_token(server):
    status, _ = call(server["base"], "/v1/alerts", token=server["write"])
    assert status == 401


def test_post_event_and_list_alert(server):
    body = {
        "source_id": "wire-1",
        "event_type": "outage",
        "text": "Power outage downtown",
        "reliability": 0.9,
        "keyword_severity": 0.8,
        "corroborations": 3,
        "age_seconds": 60,
    }
    status, payload = call(server["base"], "/v1/events", method="POST", token=server["write"], body=body)
    assert status == 201
    assert payload["status"] == "stored"
    assert payload["band"] == "critical"
    status, payload = call(server["base"], "/v1/alerts", token=server["read"])
    assert status == 200
    assert len(payload["alerts"]) == 1
    assert payload["alerts"][0]["text"] == "Power outage downtown"


def test_post_duplicate_returns_200(server):
    body = {
        "source_id": "wire-1",
        "event_type": "outage",
        "text": "Power outage downtown",
        "reliability": 0.9,
        "keyword_severity": 0.8,
        "corroborations": 3,
        "age_seconds": 60,
    }
    call(server["base"], "/v1/events", method="POST", token=server["write"], body=body)
    status, payload = call(server["base"], "/v1/events", method="POST", token=server["write"], body=body)
    assert status == 200
    assert payload["status"] == "duplicate"


def test_post_event_validates_body(server):
    status, payload = call(
        server["base"], "/v1/events", method="POST", token=server["write"],
        body={"source_id": "wire-1"},
    )
    assert status == 400
    assert "missing fields" in payload["error"]


def test_get_alert_by_id_and_missing(server):
    body = {
        "source_id": "wire-1",
        "event_type": "cyber",
        "text": "Credential stuffing attempts",
        "reliability": 0.95,
        "keyword_severity": 0.9,
        "corroborations": 5,
        "age_seconds": 30,
    }
    _, created = call(server["base"], "/v1/events", method="POST", token=server["write"], body=body)
    alert_id = created["alert_id"]
    status, payload = call(server["base"], f"/v1/alerts/{alert_id}", token=server["read"])
    assert status == 200
    assert payload["alert_id"] == alert_id
    status, _ = call(server["base"], "/v1/alerts/9999", token=server["read"])
    assert status == 404


def test_min_severity_filter(server):
    for text, reliability in [("Power outage downtown", 0.9), ("Heavy rain expected", 0.6)]:
        call(
            server["base"], "/v1/events", method="POST", token=server["write"],
            body={
                "source_id": "wire-1", "event_type": "outage", "text": text,
                "reliability": reliability, "keyword_severity": 0.8,
                "corroborations": 2, "age_seconds": 60,
            },
        )
    status, payload = call(server["base"], "/v1/alerts?min_severity=70", token=server["read"])
    assert status == 200
    assert len(payload["alerts"]) == 1
    assert payload["alerts"][0]["text"] == "Power outage downtown"
