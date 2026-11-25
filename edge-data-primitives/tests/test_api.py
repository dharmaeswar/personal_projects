import pytest

from edgeprimitives.api import EdgeAPI


@pytest.fixture
def api():
    return EdgeAPI()


def test_create_user_and_list_events(api):
    status, body = api.handle("POST", "/users", {"email": "ada@example.com", "name": "Ada"})
    assert status == 201 and body["id"] == 1
    status, body = api.handle("GET", "/users/1/events", None)
    assert status == 200 and body["events"] == []


def test_enqueue_lease_ack_flow(api):
    _, enq = api.handle("POST", "/enqueue", {"kind": "email", "to": "ada@example.com"})
    assert enq["depth"] == 1
    _, leased = api.handle("POST", "/lease", {"batch": 5})
    assert len(leased["leased"]) == 1
    mid = leased["leased"][0]["id"]
    status, acked = api.handle("POST", "/ack", {"id": mid})
    assert status == 200 and acked["acked"] == mid
    _, leased2 = api.handle("POST", "/lease", {"batch": 5})
    assert leased2["leased"] == []


def test_kv_put_get_list(api):
    status, _ = api.handle("POST", "/kv/session:1", {"value": "abc", "ttl_s": 60})
    assert status == 201
    status, body = api.handle("GET", "/kv/session:1", None)
    assert status == 200 and body["value"] == "abc"
    status, body = api.handle("GET", "/kv?prefix=session:", None)
    assert body["keys"] == ["session:1"]
    status, body = api.handle("GET", "/kv/missing", None)
    assert status == 404


def test_metrics_endpoint(api):
    api.handle("POST", "/enqueue", {"kind": "x"})
    status, body = api.handle("GET", "/metrics", None)
    assert status == 200
    assert "enqueue" in body["metrics"]
    assert body["alerts"] == []


def test_unknown_route_404(api):
    status, body = api.handle("GET", "/nope", None)
    assert status == 404


def test_bad_body_400(api):
    status, body = api.handle("POST", "/users", {"email": "only-email"})
    assert status == 400
