"""Tests for the HTTP API (stdlib http.server, exercised over real HTTP)."""

import json
import threading
import urllib.request
import urllib.error

import pytest

from care_coord.api import make_handler, serve
from care_coord.service import CareCoordinationService
from http.server import ThreadingHTTPServer


@pytest.fixture
def server():
    service = CareCoordinationService()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, service
    httpd.shutdown()
    httpd.server_close()


def _req(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_health(server):
    base, _ = server
    status, body = _req(base, "GET", "/health")
    assert status == 200
    assert body["status"] == "ok"


def test_create_and_get_plan(server):
    base, _ = server
    status, plan = _req(base, "POST", "/care-plans",
                        {"patient_ref": "PAT-0001", "title": "Follow-up"})
    assert status == 201
    assert plan["status"] == "draft"
    status, summary = _req(base, "GET", f"/care-plans/{plan['id']}")
    assert status == 200
    assert summary["plan"]["id"] == plan["id"]
    assert summary["referrals"] == []
    assert summary["tasks"] == []


def test_full_workflow_over_http(server):
    base, _ = server
    _, plan = _req(base, "POST", "/care-plans",
                   {"patient_ref": "PAT-0001", "title": "Follow-up"})
    pid = plan["id"]
    status, plan = _req(base, "POST", f"/care-plans/{pid}/transition", {"status": "active"})
    assert status == 200 and plan["status"] == "active"
    status, ref = _req(base, "POST", f"/care-plans/{pid}/referrals",
                       {"specialty": "cardiology"})
    assert status == 201
    status, ref = _req(base, "POST", f"/referrals/{ref['id']}/transition",
                       {"status": "accepted"})
    assert status == 200 and ref["status"] == "accepted"
    status, task = _req(base, "POST", f"/care-plans/{pid}/tasks",
                        {"title": "Call patient", "assignee": "team-1"})
    assert status == 201
    status, task = _req(base, "POST", f"/tasks/{task['id']}/transition",
                        {"status": "in_progress"})
    assert status == 200
    status, task = _req(base, "POST", f"/tasks/{task['id']}/transition",
                        {"status": "done"})
    assert status == 200 and task["status"] == "done"


def test_invalid_transition_returns_409(server):
    base, _ = server
    _, plan = _req(base, "POST", "/care-plans",
                   {"patient_ref": "PAT-0001", "title": "Follow-up"})
    status, body = _req(base, "POST", f"/care-plans/{plan['id']}/transition",
                        {"status": "completed"})
    assert status == 409
    assert "not allowed" in body["error"]


def test_missing_plan_returns_404(server):
    base, _ = server
    status, _ = _req(base, "GET", "/care-plans/does-not-exist")
    assert status == 404


def test_validation_error_returns_400(server):
    base, _ = server
    status, _ = _req(base, "POST", "/care-plans", {"patient_ref": "PAT-0001", "title": ""})
    assert status == 400


def test_outbox_process_endpoint(server):
    base, _ = server
    _req(base, "POST", "/care-plans", {"patient_ref": "PAT-0001", "title": "Follow-up"})
    status, body = _req(base, "POST", "/outbox/process", {})
    assert status == 200
    assert body["counts"]["delivered"] == 1
    assert len(body["delivered"]) == 1


def test_audit_endpoint_lists_entries(server):
    base, _ = server
    _req(base, "POST", "/care-plans", {"patient_ref": "PAT-0001", "title": "Follow-up"})
    status, audit = _req(base, "GET", "/audit")
    assert status == 200
    assert len(audit) == 1
    assert audit[0]["action"] == "care_plan.created"


def test_idempotent_create_over_http(server):
    base, _ = server
    _, a = _req(base, "POST", "/care-plans",
                {"patient_ref": "PAT-0001", "title": "Follow-up", "request_key": "k1"})
    _, b = _req(base, "POST", "/care-plans",
                {"patient_ref": "PAT-0001", "title": "Follow-up", "request_key": "k1"})
    assert a["id"] == b["id"]
    status, plans = _req(base, "GET", "/care-plans")
    assert status == 200
    assert len(plans) == 1
