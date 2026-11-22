"""Tests for the voice catalog + evaluation service."""
import json
import threading
import urllib.request
import urllib.error

import pytest

from voice_catalog.evaluation import composite_score, evaluate, latency_score
from voice_catalog.server import STORE, HISTORY, Handler, main  # noqa: F401  (import check)
from voice_catalog.server import ThreadingHTTPServer
from voice_catalog.service import EvalHistory, analytics_summary, run_eval
from voice_catalog.store import Store, VoiceStatus


def _voice(store=None, **kw):
    store = store or Store()
    args = {"name": "Mara — Warm Narrator", "language": "en-US",
            "style_tags": ["warm", "narrative"], "clone_source": "recording"}
    args.update(kw)
    return store.register_voice(**args), store


# -- registry -------------------------------------------------------

def test_register_and_get_voice():
    voice, store = _voice()
    assert voice.id == 1
    assert voice.status == VoiceStatus.DRAFT
    assert store.get_voice(1).name == "Mara — Warm Narrator"


def test_register_validation_rejects_bad_locale_and_source():
    store = Store()
    with pytest.raises(ValueError):
        store.register_voice("Bad", "english", clone_source="recording")
    with pytest.raises(ValueError):
        store.register_voice("Bad", "en-US", clone_source="telepathy")
    with pytest.raises(ValueError):
        store.register_voice("   ", "en-US")


def test_duplicate_voice_rejected():
    voice, store = _voice()
    with pytest.raises(ValueError, match="duplicate voice"):
        store.register_voice("mara — warm narrator", "en-US", clone_source="recording")
    # Same name in another language is a different voice.
    other = store.register_voice("Mara — Warm Narrator", "en-GB", clone_source="recording")
    assert other.id == 2


def test_search_by_language_style_status_and_name():
    store = Store()
    store.register_voice("Mara", "en-US", ["warm"], status=VoiceStatus.ACTIVE)
    store.register_voice("Lucía", "es-ES", ["calm"], status=VoiceStatus.ACTIVE)
    store.register_voice("Theo", "en-US", ["warm", "energetic"], status=VoiceStatus.DRAFT)
    assert len(store.list_voices(language="en-US")) == 2
    assert [v.name for v in store.list_voices(style="warm")] == ["Mara", "Theo"]
    assert [v.name for v in store.list_voices(status="active")] == ["Mara", "Lucía"]
    assert [v.name for v in store.list_voices(query="luc")] == ["Lucía"]


def test_version_add_and_duplicate_version_rejected():
    voice, store = _voice()
    store.add_version(voice.id, "v1", "first train")
    with pytest.raises(ValueError, match="already has version"):
        store.add_version(voice.id, "v1")
    assert [v.version for v in store.get_voice(voice.id).versions] == ["v1"]


# -- evaluation math and gates --------------------------------------

def test_composite_score_weights():
    # Perfect scores -> 1.0; latency at the gate still scores 1.0.
    assert composite_score(1.0, 1.0, 800, 1.0) == 1.0
    # 0.9 intelligibility, 0.8 similarity, 400ms latency, 0.9 coverage:
    # 0.35*0.9 + 0.35*0.8 + 0.15*1.0 + 0.15*0.9 = 0.88
    assert composite_score(0.9, 0.8, 400, 0.9) == 0.88
    assert latency_score(800) == 1.0
    assert latency_score(1600) == 0.0
    assert latency_score(1200) == 0.5
    with pytest.raises(ValueError):
        composite_score(1.2, 0.8, 400, 0.9)


def test_eval_passes_when_all_gates_hold():
    result = evaluate(1, "v1", 0.92, 0.88, 420, 0.95)
    assert result.passed is True
    assert result.quarantine is False
    assert result.failed_gates == []
    assert result.composite == 0.922  # 0.35*0.92 + 0.35*0.88 + 0.15*1.0 + 0.15*0.95


def test_eval_fails_gate_without_quarantine():
    result = evaluate(1, "v1", 0.90, 0.58, 480, 0.92)
    assert result.passed is False
    assert result.quarantine is False
    assert any("similarity" in g for g in result.failed_gates)


def test_eval_below_threshold_quarantines_voice_and_updates_status():
    store = Store()
    voice, _ = _voice(store)
    store.add_version(voice.id, "v1")
    history = EvalHistory()
    result = run_eval(store, history, voice.id, "v1", 0.52, 0.48, 1400, 0.55)
    assert result.quarantine is True
    assert result.passed is False
    assert store.get_voice(voice.id).status == VoiceStatus.QUARANTINED
    assert len(history.for_voice(voice.id)) == 1


def test_run_eval_rejects_unknown_version():
    voice, store = _voice()
    with pytest.raises(ValueError, match="no version"):
        run_eval(store, EvalHistory(), voice.id, "v9", 0.9, 0.9, 400, 0.9)


def test_analytics_summary_counts_and_pass_rate():
    store = Store()
    history = EvalHistory()
    a = store.register_voice("A", "en-US", status=VoiceStatus.ACTIVE)
    b = store.register_voice("B", "es-ES", status=VoiceStatus.ACTIVE)
    for v in (a, b):
        store.add_version(v.id, "v1")
    run_eval(store, history, a.id, "v1", 0.92, 0.88, 420, 0.95)  # pass
    run_eval(store, history, b.id, "v1", 0.52, 0.48, 1400, 0.55)  # quarantine
    summary = analytics_summary(store, history)
    assert summary["voices"] == 2
    assert summary["quarantined"] == 1
    assert summary["eval_runs"] == 2
    assert summary["pass_rate"] == 0.5
    assert summary["per_language"]["en-US"]["voices"] == 1
    assert summary["per_language"]["es-ES"]["quarantined"] == 1


# -- HTTP API ---------------------------------------------------------

@pytest.fixture()
def live_server():
    from voice_catalog import server as srv
    srv.STORE._voices.clear()
    srv.STORE._next_id = 1
    srv.HISTORY._runs.clear()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _request(base, method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


def test_api_register_search_eval_and_analytics(live_server):
    status, voice = _request(live_server, "POST", "/api/voices",
                             {"name": "Mara", "language": "en-US",
                              "style_tags": ["warm"], "clone_source": "recording",
                              "status": "active"})
    assert status == 201
    assert voice["id"] == 1
    status, _ = _request(live_server, "POST", f"/api/voices/{voice['id']}/versions",
                         {"version": "v1", "note": "first train"})
    assert status == 201
    status, found = _request(live_server, "GET", "/api/voices?language=en-US")
    assert status == 200 and len(found) == 1
    status, result = _request(live_server, "POST", f"/api/voices/{voice['id']}/evals",
                              {"version": "v1", "intelligibility": 0.92,
                               "similarity": 0.88, "latency_ms": 420, "coverage": 0.95})
    assert status == 201
    assert result["passed"] is True and result["composite"] == 0.922
    status, summary = _request(live_server, "GET", "/api/analytics")
    assert status == 200
    assert summary["voices"] == 1 and summary["pass_rate"] == 1.0
    # Duplicate register and unknown voice are rejected cleanly.
    status, err = _request(live_server, "POST", "/api/voices",
                           {"name": "Mara", "language": "en-US"})
    assert status == 400 and "duplicate" in err["error"]
    status, err = _request(live_server, "GET", "/api/voices/999")
    assert status == 404
