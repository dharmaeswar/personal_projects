import json
import threading
import urllib.request

import pytest

from signals.ingest import ingest_batch
from signals.models import Consent
from signals.serve import SignalServer, make_handler
from signals.store import Store
from signals.seed import seed_consents, seed_events
from tests.conftest import NOW, raw_event


@pytest.fixture
def server(tmp_path):
    store = Store(str(tmp_path / "store.json"))
    accepted, _ = ingest_batch(seed_events(NOW), set(), now=NOW)
    store.add_events(accepted)
    return SignalServer(store, seed_consents(), run_id="test", now=NOW)


def test_signals_for_user_returns_merged_signals(server):
    served, withheld = server.signals_for_user("user-01")
    assert served
    assert all(0.0 <= s["score"] <= 1.0 for s in served)
    assert withheld == []


def test_telemetry_opted_out_user_withholds_telemetry(server):
    served, withheld = server.signals_for_user("user-03")
    assert "telemetry" in withheld
    assert all(s["signal_type"] != "telemetry_activity" for s in served)


def test_unknown_user_gets_empty_signals(server):
    served, withheld = server.signals_for_user("user-99")
    assert served == [] and withheld == []


def test_ingest_one_accepts_valid_event(server):
    accepted, quarantined = server.ingest_one(raw_event("evt-new-1"))
    assert len(accepted) == 1 and quarantined == []


def test_ingest_one_rejects_bad_event(server):
    accepted, quarantined = server.ingest_one(raw_event("evt-new-2", user_id=""))
    assert accepted == [] and quarantined


def test_serve_is_audit_logged(server):
    before = len(server.store.data["audit"])
    server.signals_for_user("user-01")
    assert len(server.store.data["audit"]) == before + 1
    assert server.store.data["audit"][-1]["action"] == "serve"


def test_http_endpoints(server):
    from http.server import ThreadingHTTPServer
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(server))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health") as resp:
            health = json.load(resp)
        assert health["events"] == 240
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/signals/user-01") as resp:
            payload = json.load(resp)
        assert payload["user_id"] == "user-01" and payload["signals"]
    finally:
        httpd.shutdown()
