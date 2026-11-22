"""Tests for LLM training-data infrastructure (store, gates, ingestion, API)."""
import json
import threading
import urllib.request

import pytest

from llm_data_infra import ingestion, quality, service
from llm_data_infra.server import make_handler
from llm_data_infra.store import Store, content_hash
from http.server import ThreadingHTTPServer


@pytest.fixture()
def store():
    s = Store(":memory:")
    yield s
    s.close()


def _dataset(store, name="webtext-v3"):
    ds = store.create_dataset(name, "text", "data-platform", "demo corpus")
    store.create_version(ds, "1.0")
    return ds


def test_dataset_create_duplicate_and_search(store):
    ds = _dataset(store)
    assert store.get_dataset(ds)["name"] == "webtext-v3"
    with pytest.raises(ValueError, match="already exists"):
        store.create_dataset("webtext-v3", "text", "x")
    with pytest.raises(ValueError, match="must not be empty"):
        store.create_dataset("  ", "text", "x")
    assert len(store.search_datasets("webtext")) == 1
    assert store.search_datasets("nope") == []
    with pytest.raises(ValueError, match="already exists"):
        store.create_version(ds, "1.0")


def test_content_hash_dedup(store):
    ds = _dataset(store)
    payload = {"text": "hello world, this is a test record."}
    first = store.insert_record(ds, "1.0", payload, "text")
    assert first is not None
    assert store.insert_record(ds, "1.0", payload, "text") is None
    assert content_hash(payload) == content_hash(dict(payload))


def test_quality_gates():
    assert quality.run_gates({"text": "a long enough sentence here."}, "text") == []
    failures = quality.run_gates({"text": "short"}, "text")
    assert any("too short" in f for f in failures)
    failures = quality.run_gates({"text": "mail me at a@b.com please, thanks."}, "text")
    assert any("email" in f for f in failures)
    failures = quality.run_gates({"text": "my ssn is 123-45-6789 ok"}, "text")
    assert any("SSN" in f for f in failures)
    failures = quality.run_gates({"text": "a long enough sentence here."}, "video")
    assert any("unknown modality" in f for f in failures)
    failures = quality.run_gates({}, "text")
    assert failures


def test_batch_ingest_counts(store):
    ds = _dataset(store)
    records = [
        {"text": "The quick brown fox jumps over the lazy dog today."},
        {"text": "The quick brown fox jumps over the lazy dog today."},  # dup
        {"text": "tiny"},  # quarantine
        {"text": "Another long enough sentence for the corpus here."},
    ]
    result = ingestion.ingest_batch(store, ds, "1.0", records, "text")
    assert result == {"received": 4, "accepted": 2, "duplicates": 1, "quarantined": 1}
    assert len(store.list_records(ds, status="accepted")) == 2
    assert len(store.list_records(ds, status="quarantined")) == 1
    assert len(store.list_ingestion_jobs(ds)) == 1


def test_stream_ingest_matches_batch(store):
    ds = _dataset(store)
    records = [
        {"text": "Streaming record number one is long enough."},
        {"text": "Streaming record number two is long enough."},
        {"text": "Streaming record number one is long enough."},  # dup
    ]
    result = ingestion.ingest_stream(store, ds, "1.0", iter(records), "text")
    assert result == {"received": 3, "accepted": 2, "duplicates": 1, "quarantined": 0}


def test_lineage_and_search(store):
    parent = _dataset(store, "raw-web")
    child = _dataset(store, "clean-web")
    store.add_lineage(parent, "1.0", child, "1.0", "dedup+filter")
    assert len(store.list_lineage(child)) == 1
    assert store.list_lineage(child)[0]["transform"] == "dedup+filter"


def test_dashboard_aggregates(store):
    ds = _dataset(store)
    ingestion.ingest_batch(store, ds, "1.0", [
        {"text": "First long enough sentence for the corpus."},
        {"text": "Second long enough sentence for the corpus."},
    ], "text")
    dash = service.dashboard(store)
    assert dash["ingestion"]["received"] == 2
    assert dash["ingestion"]["accept_rate"] == pytest.approx(1.0)
    assert dash["pipeline_health"] == "healthy"
    assert dash["datasets"][0]["name"] == "webtext-v3"


def test_http_api_round_trip(store):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        def call(method, path, payload=None):
            req = urllib.request.Request(
                base + path, method=method,
                data=json.dumps(payload).encode() if payload is not None else None,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req) as resp:
                return resp.status, json.loads(resp.read() or b"{}")

        status, ds = call("POST", "/api/datasets",
                          {"name": "webtext-v3", "modality": "text", "owner": "dp"})
        assert status == 201
        status, ver = call("POST", f"/api/datasets/{ds['id']}/versions", {"version": "1.0"})
        assert status == 201
        status, result = call("POST", "/api/ingest/batch", {
            "dataset_id": ds["id"], "version": "1.0", "modality": "text",
            "records": [{"text": "A long enough sentence for ingestion."}]})
        assert status == 201 and result["accepted"] == 1
        status, dash = call("GET", "/api/dashboard")
        assert status == 200 and dash["ingestion"]["accepted"] == 1
        status, found = call("GET", "/api/datasets?q=webtext")
        assert status == 200 and len(found) == 1
        with urllib.request.urlopen(base + "/") as resp:
            html = resp.read().decode()
        assert "webtext-v3" in html and "Catalog" in html
    finally:
        server.shutdown()
        server.server_close()
