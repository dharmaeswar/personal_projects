import json
import urllib.error
import urllib.request


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health(api_server):
    status, body = get(api_server, "/health")
    assert status == 200
    assert body == {"status": "ok"}


def test_list_plans_schema(api_server):
    status, body = get(api_server, "/plans")
    assert status == 200
    assert len(body["plans"]) == 2
    for plan in body["plans"]:
        assert set(plan) == {"id", "name", "price", "data_gb"}
        assert plan["price"] > 0 and plan["data_gb"] > 0


def test_get_plan_by_id(api_server):
    status, body = get(api_server, "/plans/2")
    assert status == 200
    assert body["name"] == "Plus"


def test_get_missing_plan_returns_404(api_server):
    status, body = get(api_server, "/plans/999")
    assert status == 404
    assert "error" in body


def test_unknown_route_returns_404(api_server):
    status, _ = get(api_server, "/nope")
    assert status == 404
