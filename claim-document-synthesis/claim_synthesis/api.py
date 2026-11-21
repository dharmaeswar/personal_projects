"""HTTP API for the claim-synthesis service (Python standard library only).

Endpoints (all JSON):
- POST /claims                  ingest one claim document
- GET  /claims?tenant_id=...    list a tenant's claims
- GET  /claims/<id>?tenant_id=...  one claim (tenant-scoped)
- GET  /review-queue?tenant_id=...  pending reviews for a tenant
- POST /claims/<id>/review      {tenant_id, action, actor, corrections?, reason?}

Errors: 400 bad request, 403 cross-tenant access, 404 unknown claim.
Run: ``python -m claim_synthesis.api [--port 8000]``.
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .documents import generate_documents
from .service import ClaimSynthesisService


def _send(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def make_handler(service: ClaimSynthesisService):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep test output quiet
            pass

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", 0))
            if not length:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _tenant(self, query: dict) -> str | None:
            values = query.get("tenant_id")
            return values[0] if values else None

        def do_POST(self):
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/claims":
                    claim = service.ingest_claim(self._read_json())
                    _send(self, 201, claim)
                elif parsed.path.startswith("/claims/") and parsed.path.endswith("/review"):
                    claim_id = parsed.path.split("/")[2]
                    body = self._read_json()
                    claim = service.review_claim(
                        claim_id, body["tenant_id"], body["action"],
                        body.get("actor", "reviewer"),
                        body.get("corrections"), body.get("reason", ""))
                    _send(self, 200, claim)
                else:
                    _send(self, 404, {"error": "unknown endpoint"})
            except (ValueError, KeyError) as exc:
                _send(self, 400, {"error": str(exc)})
            except PermissionError as exc:
                _send(self, 403, {"error": str(exc)})

        def do_GET(self):
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            tenant_id = self._tenant(query)
            try:
                if parsed.path == "/claims":
                    if not tenant_id:
                        _send(self, 400, {"error": "tenant_id query param is required"})
                    else:
                        _send(self, 200, {"claims": service.list_claims(tenant_id)})
                elif parsed.path == "/review-queue":
                    if not tenant_id:
                        _send(self, 400, {"error": "tenant_id query param is required"})
                    else:
                        _send(self, 200, {"queue": service.review_queue(tenant_id)})
                elif parsed.path.startswith("/claims/"):
                    claim_id = parsed.path.split("/")[2]
                    if not tenant_id:
                        _send(self, 400, {"error": "tenant_id query param is required"})
                    else:
                        _send(self, 200, service.get_claim(claim_id, tenant_id))
                else:
                    _send(self, 404, {"error": "unknown endpoint"})
            except (ValueError, KeyError) as exc:
                _send(self, 400, {"error": str(exc)})
            except PermissionError as exc:
                _send(self, 403, {"error": str(exc)})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Claim synthesis API server.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--seed", action="store_true",
                        help="Pre-load the seeded synthetic documents.")
    args = parser.parse_args()
    service = ClaimSynthesisService()
    if args.seed:
        for document in generate_documents():
            service.ingest_claim(document)
        print(f"Seeded {service.store.count()} claims.")
    server = ThreadingHTTPServer(("127.0.0.1", args.port),
                                 make_handler(service))
    print(f"Claim synthesis API on http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
