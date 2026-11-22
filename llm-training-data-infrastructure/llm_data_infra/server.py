"""Stdlib-only HTTP API + dashboard for LLM training-data infrastructure.

Routes (all JSON except /):
  GET  /                              dashboard HTML page
  GET  /api/dashboard                 catalog + ingestion + health
  GET  /api/datasets?modality=        list datasets
  POST /api/datasets                  {"name","modality","owner","description"?}
  GET  /api/datasets/<id>             dataset stats
  GET  /api/datasets?q=               search catalog by name/description
  POST /api/datasets/<id>/versions    {"version"}
  POST /api/ingest/batch              {"dataset_id","version","records":[...],"modality"}
  POST /api/ingest/stream             {"dataset_id","version","records":[...],"modality"}
  GET  /api/datasets/<id>/records?version=&status=
  POST /api/lineage                   {"parent_id","parent_version","child_id","child_version","transform"}
  GET  /api/datasets/<id>/lineage
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import ingestion, service
from .store import Store


def make_handler(store: Store):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _send_json(self, payload, status=200):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html: str):
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length) or b"{}")

        def _route(self, method):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)
            parts = [p for p in path.split("/") if p]
            try:
                if method == "GET" and path == "/":
                    return self._send_html(dashboard_page(service.dashboard(store)))
                if method == "GET" and path == "/api/dashboard":
                    return self._send_json(service.dashboard(store))
                if method == "GET" and parts == ["api", "datasets"]:
                    if "q" in query:
                        return self._send_json(store.search_datasets(query["q"][0]))
                    return self._send_json(
                        store.list_datasets(query.get("modality", [None])[0]))
                if method == "POST" and parts == ["api", "datasets"]:
                    body = self._read_json()
                    ds_id = store.create_dataset(
                        body["name"], body.get("modality", "text"),
                        body.get("owner", "unknown"), body.get("description", ""))
                    return self._send_json(store.get_dataset(ds_id), status=201)
                if method == "GET" and len(parts) == 3 and parts[:2] == ["api", "datasets"]:
                    return self._send_json(service.dataset_stats(store, int(parts[2])))
                if method == "POST" and len(parts) == 4 and parts[:2] == ["api", "datasets"] and parts[3] == "versions":
                    body = self._read_json()
                    ver_id = store.create_version(int(parts[2]), body["version"])
                    versions = store.list_versions(int(parts[2]))
                    return self._send_json(
                        [v for v in versions if v["id"] == ver_id][0], status=201)
                if method == "POST" and parts == ["api", "ingest", "batch"]:
                    body = self._read_json()
                    return self._send_json(ingestion.ingest_batch(
                        store, body["dataset_id"], body["version"],
                        body["records"], body.get("modality", "text")), status=201)
                if method == "POST" and parts == ["api", "ingest", "stream"]:
                    body = self._read_json()
                    return self._send_json(ingestion.ingest_stream(
                        store, body["dataset_id"], body["version"],
                        iter(body["records"]), body.get("modality", "text")), status=201)
                if method == "GET" and len(parts) == 4 and parts[:2] == ["api", "datasets"] and parts[3] == "records":
                    ds_id = int(parts[2])
                    return self._send_json(store.list_records(
                        ds_id, query.get("version", [None])[0],
                        query.get("status", [None])[0]))
                if method == "POST" and parts == ["api", "lineage"]:
                    body = self._read_json()
                    edge_id = store.add_lineage(
                        body["parent_id"], body["parent_version"],
                        body["child_id"], body["child_version"], body["transform"])
                    return self._send_json({"lineage_id": edge_id}, status=201)
                if method == "GET" and len(parts) == 4 and parts[:2] == ["api", "datasets"] and parts[3] == "lineage":
                    return self._send_json(store.list_lineage(int(parts[2])))
                return self._send_json({"error": "not found"}, status=404)
            except (ValueError, KeyError) as exc:
                return self._send_json({"error": str(exc)}, status=400)

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

    return Handler


def dashboard_page(data: dict) -> str:
    rows = "".join(
        f"<tr><td>{d['name']}</td><td>{d['modality']}</td>"
        f"<td>{d['records']}</td><td>{d['accepted']}</td>"
        f"<td>{d['quarantined']}</td><td>{d['dedup_rate']:.2%}</td></tr>"
        for d in data["datasets"]
    )
    ing = data["ingestion"]
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>LLM Training Data Infrastructure — Dashboard</title></head><body>
<h1>LLM Training Data Infrastructure</h1>
<h2>Catalog</h2>
<table border="1"><tr><th>Dataset</th><th>Modality</th><th>Records</th>
<th>Accepted</th><th>Quarantined</th><th>Dedup rate</th></tr>{rows}</table>
<h2>Ingestion</h2>
<p>Jobs: {ing['jobs']} | Received: {ing['received']} | Accepted: {ing['accepted']} |
Duplicates: {ing['duplicates']} | Quarantined: {ing['quarantined']} |
Accept rate: {ing['accept_rate']:.2%}</p>
<h2>Pipeline health: {data['pipeline_health']}</h2>
</body></html>"""


def run(store: Store, host: str = "127.0.0.1", port: int = 8000):
    server = ThreadingHTTPServer((host, port), make_handler(store))
    print(f"LLM training-data infrastructure on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run(Store("llm_data_infra.db"))
