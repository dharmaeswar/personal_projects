"""HTTP layer: REST API plus the browser dashboard (stdlib only).

Endpoints:
  GET  /                     dashboard UI
  GET  /health               liveness check
  GET  /metrics              Prometheus-format counters
  GET  /v1/inventory         stock per SKU and warehouse
  GET  /v1/orders            all orders
  GET  /v1/orders/{id}       one order
  POST /v1/orders            {"sku", "qty", "idempotency_key"?, "warehouse"?}
  POST /v1/orders/{id}/fulfill
  POST /v1/orders/{id}/cancel
  POST /v1/restock          {"sku", "warehouse", "qty"}
  GET  /v1/events?topic=&after=   event log, newest last
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .events import EventValidationError
from .service import InventoryService, OrderError
from .store import demo_store

UI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui.html")


def make_handler(service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep test output clean
            pass

        # -- helpers -----------------------------------------------------
        def _json(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self):
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            try:
                return json.loads(self.rfile.read(length))
            except json.JSONDecodeError as exc:
                raise OrderError(f"invalid JSON: {exc}")

        # -- routes ------------------------------------------------------
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/":
                with open(UI_PATH, "rb") as fh:
                    body = fh.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path == "/health":
                self._json(200, {"status": "ok"})
            elif parsed.path == "/metrics":
                text = (
                    "# HELP inventory_orders_total Orders created\n"
                    "# TYPE inventory_orders_total counter\n"
                    f"inventory_orders_total {len(service.store.orders)}\n"
                    "# HELP inventory_events_total Events published\n"
                    "# TYPE inventory_events_total counter\n"
                    f"inventory_events_total {len(service.bus)}\n"
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4")
                self.send_header("Content-Length", str(len(text)))
                self.end_headers()
                self.wfile.write(text)
            elif parsed.path == "/v1/inventory":
                self._json(200, service.store.inventory_view())
            elif parsed.path == "/v1/orders":
                self._json(200, service.list_orders())
            elif parsed.path.startswith("/v1/orders/"):
                order_id = parsed.path.split("/")[3]
                order = service.store.orders.get(order_id)
                if order is None:
                    self._json(404, {"error": f"unknown order: {order_id}"})
                else:
                    self._json(200, order)
            elif parsed.path == "/v1/events":
                query = parse_qs(parsed.query)
                topic = query.get("topic", [None])[0]
                after = int(query.get("after", ["0"])[0])
                self._json(200, service.bus.events(topic=topic, after=after))
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            parsed = urlparse(self.path)
            try:
                body = self._read_json()
                if parsed.path == "/v1/orders":
                    order = service.create_order(
                        body.get("sku"),
                        body.get("qty"),
                        idempotency_key=body.get("idempotency_key"),
                        warehouse=body.get("warehouse"),
                    )
                    self._json(201, order)
                elif parsed.path.startswith("/v1/orders/") and parsed.path.endswith("/fulfill"):
                    order_id = parsed.path.split("/")[3]
                    self._json(200, service.fulfill_order(order_id))
                elif parsed.path.startswith("/v1/orders/") and parsed.path.endswith("/cancel"):
                    order_id = parsed.path.split("/")[3]
                    self._json(200, service.cancel_order(order_id))
                elif parsed.path == "/v1/restock":
                    self._json(
                        200,
                        service.restock(body.get("sku"), body.get("warehouse"), body.get("qty")),
                    )
                else:
                    self._json(404, {"error": "not found"})
            except (OrderError, EventValidationError, KeyError) as exc:
                self._json(400, {"error": str(exc)})

    return Handler


def run(port=8000):
    service = InventoryService(store=demo_store())
    server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(service))
    print(f"Inventory Orchestration Service on http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run(port=int(os.environ.get("PORT", "8000")))
