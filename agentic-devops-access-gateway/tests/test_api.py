import json
import threading
import urllib.request
import urllib.error

import pytest

from gateway import AccessGateway
from gateway.api import serve


@pytest.fixture
def server():
    gw = AccessGateway()
    gw.registry.register("srv-prod-1", "prod-1", "prod", "10.0.1.21:22")
    token = gw.tokens.issue("agent-deploy-1", "deployer",
                            ["deploy:service:checkout", "read:service:checkout"],
                            "prod")
    httpd = serve(gw, port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, token
    httpd.shutdown()
    httpd.server_close()


def _req(base, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=headers,
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health_no_auth(server):
    base, _ = server
    status, body = _req(base, "/health")
    assert status == 200 and body["status"] == "ok"


def test_execute_via_http(server):
    base, token = server
    status, body = _req(base, "/v1/execute", token, {
        "action": "deploy", "resource": "service:checkout",
        "server_id": "srv-prod-1", "idempotency_key": "http-1"})
    assert status == 200
    assert body["allowed"] is True


def test_execute_without_token_401(server):
    base, _ = server
    status, _ = _req(base, "/v1/execute", None, {
        "action": "deploy", "resource": "service:checkout",
        "server_id": "srv-prod-1"})
    assert status == 401


def test_execute_forbidden_action_403(server):
    base, token = server
    status, body = _req(base, "/v1/execute", token, {
        "action": "delete", "resource": "service:checkout",
        "server_id": "srv-prod-1"})
    assert status == 403
    assert body["allowed"] is False


def test_servers_and_audit_endpoints(server):
    base, token = server
    status, body = _req(base, "/v1/servers", token)
    assert status == 200 and len(body["servers"]) == 1
    status, body = _req(base, "/v1/audit", token)
    assert status == 200 and body["entries"] == []
