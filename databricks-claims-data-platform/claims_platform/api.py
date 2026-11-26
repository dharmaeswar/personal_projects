"""Read API exposing the gold/silver datasets to applications and analytics.

Stdlib-only HTTP server (no framework dependency). Endpoints read the CSV
mirrors the pipeline writes under lakehouse/ so the API works anywhere the
pipeline output exists.

  GET /health
  GET /claims?plan=<plan>&diag_group=<group>&limit=<n>&offset=<n>
  GET /claims/<claim_id>
  GET /members/<member_id>
  GET /gold/daily?service_date=YYYY-MM-DD
  GET /gold/monthly?service_month=YYYY-MM

Pagination defaults: limit=50, max limit=500 — large datasets are exposed in
pages, never as one unbounded dump. Responses are JSON.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pandas as pd

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAKEHOUSE = os.path.join(BASE, "lakehouse")


def _load(name):
    path = os.path.join(LAKEHOUSE, name, "data.csv")
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)


def _page(frame, query):
    limit = min(int(query.get("limit", ["50"])[0]), 500)
    offset = max(int(query.get("offset", ["0"])[0]), 0)
    total = len(frame)
    rows = frame.iloc[offset:offset + limit].to_dict(orient="records")
    return {"total": int(total), "limit": limit, "offset": offset, "rows": rows}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, payload):
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        parts = [p for p in parsed.path.split("/") if p]

        if parts == ["health"]:
            return self._send(200, {"status": "ok"})
        if parts == ["claims"]:
            silver = _load("silver/claims")
            if silver is None:
                return self._send(503, {"error": "silver layer not built; run run_pipeline.py first"})
            frame = silver
            if "plan" in query:
                frame = frame[frame["plan"] == query["plan"][0]]
            if "diag_group" in query:
                frame = frame[frame["diag_group"] == query["diag_group"][0]]
            if "paid_band" in query:
                frame = frame[frame["paid_band"] == query["paid_band"][0]]
            return self._send(200, _page(frame, query))
        if len(parts) == 2 and parts[0] == "claims":
            silver = _load("silver/claims")
            if silver is None:
                return self._send(503, {"error": "silver layer not built"})
            hit = silver[silver["claim_id"] == parts[1]]
            if hit.empty:
                return self._send(404, {"error": "claim not found"})
            return self._send(200, hit.iloc[0].to_dict())
        if len(parts) == 2 and parts[0] == "members":
            # Member dimension lives in the silver join; rebuild the lookup from silver.
            silver = _load("silver/claims")
            if silver is None:
                return self._send(503, {"error": "silver layer not built"})
            cols = ["member_id", "plan", "state", "enrolled_date", "age_band"]
            hit = silver.drop_duplicates("member_id")[cols]
            hit = hit[hit["member_id"] == parts[1]]
            if hit.empty:
                return self._send(404, {"error": "member not found"})
            return self._send(200, hit.iloc[0].to_dict())
        if parts == ["gold", "daily"]:
            gold = _load("gold/daily")
            if gold is None:
                return self._send(503, {"error": "gold layer not built"})
            if "service_date" in query:
                gold = gold[gold["service_date"] == query["service_date"][0]]
            return self._send(200, _page(gold, query))
        if parts == ["gold", "monthly"]:
            gold = _load("gold/monthly")
            if gold is None:
                return self._send(503, {"error": "gold layer not built"})
            if "service_month" in query:
                gold = gold[gold["service_month"] == query["service_month"][0]]
            return self._send(200, _page(gold, query))
        return self._send(404, {"error": "unknown endpoint"})


def run_server(port=0):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    return server


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = run_server(port)
    print(f"claims API on http://127.0.0.1:{server.server_address[1]}")
    server.serve_forever()
