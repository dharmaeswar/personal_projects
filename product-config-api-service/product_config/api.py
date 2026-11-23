"""Local REST API server (stdlib only).

Serves the same Lambda-style handlers over HTTP so the service can be
developed and tested without AWS:

  POST   /v1/products                  create a config (version 1, draft)
  GET    /v1/products/{id}             latest version (?version=N for one)
  GET    /v1/products/{id}/published  latest published version
  POST   /v1/products/{id}/publish?version=N   run the publish workflow
  GET    /v1/products/{id}/suggest?version=N   defaults, warnings, score
  GET    /health                       liveness check

Run:  python run_api.py   (listens on $PORT, default 8080)
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from product_config import handlers


def _dispatch(method: str, path: str, query: dict, body: bytes) -> tuple[int, dict]:
    parts = [p for p in path.split("/") if p]
    event = {
        "body": body.decode("utf-8") if body else "",
        "pathParameters": {},
        "queryStringParameters": {k: v[0] for k, v in query.items()},
    }
    if parts == ["health"] and method == "GET":
        return 200, {"status": "ok"}
    if parts == ["v1", "products"] and method == "POST":
        result = handlers.create_config(event)
        return result["statusCode"], json.loads(result["body"])
    if len(parts) == 3 and parts[:2] == ["v1", "products"] and method == "GET":
        event["pathParameters"] = {"product_id": parts[2]}
        result = handlers.get_config(event)
        return result["statusCode"], json.loads(result["body"])
    if len(parts) == 4 and parts[:2] == ["v1", "products"]:
        event["pathParameters"] = {"product_id": parts[2]}
        if parts[3] == "published" and method == "GET":
            result = handlers.get_published_config(event)
        elif parts[3] == "publish" and method == "POST":
            result = handlers.publish_config(event)
        elif parts[3] == "suggest" and method == "GET":
            result = handlers.suggest_config(event)
        else:
            return 404, {"error": "not found"}
        return result["statusCode"], json.loads(result["body"])
    return 404, {"error": "not found"}


class Handler(BaseHTTPRequestHandler):
    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        try:
            status, payload = _dispatch(method, parsed.path, parse_qs(parsed.query), body)
        except Exception as exc:  # never leak a stack trace to the client
            status, payload = 500, {"error": f"internal error: {exc}"}
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def log_message(self, *args):
        pass


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"product-config-api listening on :{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
