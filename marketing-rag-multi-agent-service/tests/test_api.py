import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from marketing_rag.api import Handler


@pytest.fixture(scope="module")
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    httpd.shutdown()


def _get(base, path):
    with urllib.request.urlopen(base + path) as resp:
        return resp.status, json.loads(resp.read())


def _post(base, path, payload):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read())


def test_health(server):
    status, body = _get(server, "/health")
    assert status == 200
    assert body == {"status": "ok"}


def test_campaigns(server):
    status, body = _get(server, "/campaigns")
    assert status == 200
    assert len(body["campaigns"]) == 8
    best = max(body["campaigns"], key=lambda c: c["roi"])
    assert best["id"] == "CMP-007" and best["roi"] == 5.5


def test_ask_endpoint(server):
    status, body = _post(server, "/ask", {"question": "Which campaign has the best return on spend?"})
    assert status == 200
    assert "Partner Co-Marketing" in body["answer"]
    assert body["validation"]["passed"] is True


def test_ask_missing_question(server):
    req = urllib.request.Request(server + "/ask", data=b"{}",
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(req)
    assert excinfo.value.code == 400


def test_evaluate_endpoint(server):
    status, body = _post(server, "/evaluate", {})
    assert status == 200
    assert body["cases"] == 8
    assert body["faithfulness"] == 1.0


def test_unknown_path(server):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(server + "/nope")
    assert excinfo.value.code == 404
