"""HTTP service for Freight Ops: JSON REST API + the shipment-board UI.

Routes:
  GET  /                  shipment board UI (HTML/CSS/JS, no framework)
  GET  /health            {"status": "ok"}
  GET  /metrics           Prometheus text format (request counts, shipments by status)
  GET  /v1/dashboard      counts by status, totals, on-time rate
  GET  /v1/shipments[?status=]   list shipments
  POST /v1/shipments      create a shipment
  GET  /v1/shipments/{id}        one shipment with its events
  POST /v1/shipments/{id}/events append a tracking event
  POST /v1/shipments/{id}/progress  update distance remaining
  GET  /v1/shipments/{id}/eta     ETA estimate

Standard library only. Run with: python run_service.py [port]
"""

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from . import eta as eta_mod
from .metrics import Metrics
from .store import ShipmentStore, ValidationError, validate_event, validate_shipment

_UI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui.html")

_ID_RE = re.compile(r"^/v1/shipments/(\d+)(?:/(events|progress|eta))?$")


def make_handler(store, metrics):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # keep test output clean
            pass

        def _send(self, status, payload, content_type="application/json"):
            body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            metrics.record_request(self.command, self._route_label(), status)

        def _route_label(self):
            path = urlparse(self.path).path
            if _ID_RE.match(path):
                return "/v1/shipments/{id}"
            return path

        def _read_json(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            if not raw:
                return {}
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                raise ValidationError("body must be valid JSON")
            if not isinstance(parsed, dict):
                raise ValidationError("body must be a JSON object")
            return parsed

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                if path == "/":
                    with open(_UI_PATH, "rb") as fh:
                        self._send(200, fh.read(), "text/html; charset=utf-8")
                elif path == "/health":
                    self._send(200, {"status": "ok"})
                elif path == "/metrics":
                    metrics.set_shipments(store.dashboard()["by_status"])
                    self._send(200, metrics.render().encode(), "text/plain; version=0.0.4")
                elif path == "/v1/dashboard":
                    self._send(200, store.dashboard())
                elif path == "/v1/shipments":
                    status = parse_qs(parsed.query).get("status", [None])[0]
                    self._send(200, {"shipments": store.list(status)})
                else:
                    match = _ID_RE.match(path)
                    if match and match.group(2) is None:
                        shipment = store.get(int(match.group(1)))
                        if shipment is None:
                            self._send(404, {"error": "shipment not found"})
                        else:
                            self._send(200, shipment)
                    elif match and match.group(2) == "eta":
                        shipment = store.get(int(match.group(1)))
                        if shipment is None:
                            self._send(404, {"error": "shipment not found"})
                        else:
                            self._send(200, eta_mod.estimate_eta(shipment))
                    else:
                        self._send(404, {"error": "not found"})
            except ValidationError as exc:
                self._send(400, {"error": str(exc)})

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                body = self._read_json()
                if path == "/v1/shipments":
                    shipment = store.create(validate_shipment(body))
                    self._send(201, shipment)
                    return
                match = _ID_RE.match(path)
                if not match or match.group(2) is None:
                    self._send(404, {"error": "not found"})
                    return
                shipment_id = int(match.group(1))
                action = match.group(2)
                if action == "events":
                    shipment = store.add_event(shipment_id, validate_event(body))
                    if shipment is None:
                        self._send(404, {"error": "shipment not found"})
                    else:
                        self._send(200, shipment)
                elif action == "progress":
                    shipment = store.update_progress(
                        shipment_id, body.get("distance_remaining_miles")
                    )
                    if shipment is None:
                        self._send(404, {"error": "shipment not found"})
                    else:
                        self._send(200, shipment)
                else:
                    self._send(404, {"error": "not found"})
            except ValidationError as exc:
                self._send(400, {"error": str(exc)})

    return Handler


def create_server(port=0, host="127.0.0.1"):
    store = ShipmentStore()
    metrics = Metrics()
    return ThreadingHTTPServer((host, port), make_handler(store, metrics))


def run(port=8000):
    server = create_server(port)
    print(f"Freight Ops listening on http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    import sys

    run(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
