"""Tests for the public website platform API (content, forms, analytics, consent)."""

import json
import urllib.request
import urllib.error

import pytest

from website_platform.app import create_server
from website_platform.store import Store
import website_platform.app as app_module


@pytest.fixture()
def server():
    """Start the API on a free port with a fresh store per test."""
    app_module.STORE = Store()
    httpd = create_server(port=0)
    import threading
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]
    yield base
    httpd.shutdown()
    httpd.server_close()


def request(base, method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def test_health(server):
    status, body = request(server, "GET", "/health")
    assert status == 200 and body["status"] == "ok"


def test_list_pages(server):
    status, body = request(server, "GET", "/api/content/pages")
    assert status == 200
    slugs = [p["slug"] for p in body["pages"]]
    assert "home" in slugs and "pricing" in slugs


def test_get_page_and_missing_page(server):
    status, body = request(server, "GET", "/api/content/pages/home")
    assert status == 200 and body["title"] == "Ship what's next"
    assert body["blocks"][0]["type"] == "hero"
    status, _ = request(server, "GET", "/api/content/pages/nope")
    assert status == 404


def test_form_submission_success(server):
    status, body = request(server, "POST", "/api/forms/contact/submissions",
                           {"name": "Ada", "email": "ada@example.com",
                            "message": "Hello"},
                           {"Idempotency-Key": "key-1"})
    assert status == 201 and body["id"] == "sub-0001"
    assert body["duplicate"] is False


def test_form_replay_is_idempotent(server):
    payload = {"name": "Ada", "email": "ada@example.com", "message": "Hello"}
    headers = {"Idempotency-Key": "key-2"}
    request(server, "POST", "/api/forms/contact/submissions", payload, headers)
    status, body = request(server, "POST", "/api/forms/contact/submissions",
                           payload, headers)
    assert status == 200 and body["duplicate"] is True
    assert body["id"] == "sub-0001"


def test_form_missing_fields_and_bad_email(server):
    status, body = request(server, "POST", "/api/forms/contact/submissions",
                           {"name": "Ada"}, {"Idempotency-Key": "key-3"})
    assert status == 400 and "email" in body["fields"]
    status, body = request(server, "POST", "/api/forms/newsletter/submissions",
                           {"email": "not-an-email"},
                           {"Idempotency-Key": "key-4"})
    assert status == 400 and body["error"] == "invalid email"


def test_form_requires_idempotency_key_and_known_form(server):
    status, body = request(server, "POST", "/api/forms/contact/submissions",
                           {"name": "Ada", "email": "a@b.co", "message": "x"})
    assert status == 400 and "Idempotency-Key" in body["error"]
    status, body = request(server, "POST", "/api/forms/unknown/submissions",
                           {"email": "a@b.co"}, {"Idempotency-Key": "key-5"})
    assert status == 404


def test_consent_defaults_and_update(server):
    status, body = request(server, "GET", "/api/consent?visitor_id=v-1")
    assert status == 200
    assert body == {"analytics": False, "marketing": False}
    status, body = request(server, "POST", "/api/consent",
                           {"visitor_id": "v-1", "analytics": True})
    assert status == 200 and body["analytics"] is True
    assert body["marketing"] is False
    status, body = request(server, "GET", "/api/consent?visitor_id=v-1")
    assert body["analytics"] is True


def test_analytics_blocked_without_consent(server):
    status, body = request(server, "POST", "/api/analytics/events",
                           {"visitor_id": "v-2",
                            "events": [{"name": "page_view"}]})
    assert status == 403


def test_analytics_accepted_with_consent(server):
    request(server, "POST", "/api/consent",
            {"visitor_id": "v-3", "analytics": True})
    status, body = request(server, "POST", "/api/analytics/events",
                           {"visitor_id": "v-3", "events": [
                               {"name": "page_view", "properties": {"path": "/"}},
                               {"name": "cta_click", "properties": {"id": "signup"}},
                           ]})
    assert status == 202 and body["accepted"] == 2


def test_analytics_rejects_bad_batch(server):
    request(server, "POST", "/api/consent",
            {"visitor_id": "v-4", "analytics": True})
    status, _ = request(server, "POST", "/api/analytics/events",
                        {"visitor_id": "v-4", "events": [{"properties": {}}]})
    assert status == 400
    status, _ = request(server, "POST", "/api/analytics/events",
                        {"visitor_id": "v-4",
                         "events": [{"name": "x"}] * 51})
    assert status == 400


def test_metrics_counts_requests_and_events(server):
    request(server, "GET", "/health")
    request(server, "POST", "/api/consent",
            {"visitor_id": "v-5", "analytics": True})
    request(server, "POST", "/api/analytics/events",
            {"visitor_id": "v-5", "events": [{"name": "page_view"}]})
    req = urllib.request.Request(server + "/metrics")
    with urllib.request.urlopen(req) as resp:
        text = resp.read().decode()
    assert "website_requests_total" in text
    assert "website_analytics_events_total 1" in text


def test_unknown_route_404(server):
    status, _ = request(server, "GET", "/nope")
    assert status == 404
