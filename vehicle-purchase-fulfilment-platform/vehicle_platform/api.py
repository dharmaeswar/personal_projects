"""REST API plus a small GraphQL-style query endpoint, stdlib only.

Endpoints:
  GET  /health
  GET  /                         dashboard page (HTML)
  GET  /v1/vehicles/{vin}
  POST /v1/orders                create (Idempotency-Key supported)
  GET  /v1/orders/{id}
  POST /v1/orders/{id}/advance   {"to": "<STATE>"}
  POST /v1/graphql               {"query": "{ vehicle(vin: \"...\") { make priceCents } }"}

Every error uses one shape: {"error": {"code": ..., "message": ...}}.
Run: python3 -m vehicle_platform.api (serves on port 8080).
"""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .events import EventLog
from .orders import OrderError, rebuild_from_events, validate_new_order
from .store import OrderStore, VehicleDocStore

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

VEHICLE_FIELDS = {
    "vin", "make", "model", "year", "mileage", "listPriceCents",
    "status", "features",
}
ORDER_FIELDS = {
    "orderId", "vin", "customerId", "listPriceCents", "status",
    "totalCents",
}


class Service:
    """Wires the order store, vehicle docs, and event log together."""

    def __init__(self, data_dir: str | Path = DATA_DIR):
        self.data_dir = Path(data_dir)
        self.orders = OrderStore(self.data_dir / "orders.db")
        self.vehicles = VehicleDocStore(self.data_dir / "vehicles")
        self.events = EventLog()
        self._idempotency: dict[str, dict] = {}
        self._lock = threading.Lock()

    def seed_vehicle(self, doc: dict) -> None:
        self.vehicles.put_vehicle(doc)

    def create_order(self, payload: dict, idempotency_key: str | None = None):
        with self._lock:
            if idempotency_key and idempotency_key in self._idempotency:
                return self._idempotency[idempotency_key], True
            order = validate_new_order(payload)
            vehicle = self.vehicles.get_vehicle(order.vin)
            if vehicle is None:
                raise OrderError(f"no vehicle listed for VIN {order.vin}")
            if vehicle.get("status") not in (None, "AVAILABLE"):
                raise OrderError(f"vehicle {order.vin} is not available")
            self.orders.save_order(order)
            self.vehicles.mark_reserved(order.vin, order.order_id)
            self.events.publish(
                "order-events", order.order_id,
                {"type": "ORDER_CREATED", **order.to_dict()},
            )
            result = order.to_dict()
            if idempotency_key:
                self._idempotency[idempotency_key] = result
            return result, False

    def advance_order(self, order_id: str, to_state: str) -> dict:
        with self._lock:
            order = self.orders.get_order(order_id)
            if order is None:
                raise OrderError(f"unknown order: {order_id}")
            order.advance(to_state)
            self.orders.save_order(order)
            self.events.publish(
                "order-events", order.order_id,
                {"type": "ORDER_ADVANCED", **order.to_dict()},
            )
            return order.to_dict()

    def replay_order(self, order_id: str):
        records = self.events.read_key("order-events", order_id)
        return rebuild_from_events(order_id, records)

    def graphql_query(self, query: str) -> dict:
        """Minimal GraphQL-style query: vehicle(vin) / order(id) + fields."""
        m = re.search(
            r"(vehicle|order)\(\s*(vin|id)\s*:\s*\"([^\"]+)\"\s*\)\s*\{([^}]*)\}",
            query,
        )
        if not m:
            raise OrderError("unsupported query: use vehicle(vin: \"...\")"
                             " or order(id: \"...\") with a field list")
        kind, _arg, key, fields_raw = m.groups()
        fields = [f.strip() for f in fields_raw.split() if f.strip()]
        if kind == "vehicle":
            doc = self.vehicles.get_vehicle(key)
            if doc is None:
                raise OrderError(f"no vehicle listed for VIN {key}")
            allowed = VEHICLE_FIELDS
            source = {
                "vin": doc["vin"], "make": doc["make"], "model": doc["model"],
                "year": doc["year"], "mileage": doc["mileage"],
                "listPriceCents": doc["list_price_cents"],
                "status": doc.get("status", "AVAILABLE"),
                "features": doc.get("features", []),
            }
        else:
            order = self.orders.get_order(key)
            if order is None:
                raise OrderError(f"unknown order: {key}")
            allowed = ORDER_FIELDS
            d = order.to_dict()
            source = {
                "orderId": d["order_id"], "vin": d["vin"],
                "customerId": d["customer_id"],
                "listPriceCents": d["list_price_cents"],
                "status": d["status"], "totalCents": d["total_cents"],
            }
        bad = [f for f in fields if f not in allowed]
        if bad:
            raise OrderError(f"unknown fields for {kind}: {', '.join(bad)}")
        return {f: source[f] for f in fields}


DASHBOARD_HTML = """<!doctype html><html><head><title>Vehicle Purchase Fulfilment</title></head>
<body><h1>Vehicle Purchase Fulfilment Platform</h1>
<p>REST API for online vehicle purchases: reserve, inspect, finance, schedule delivery.</p>
<ul><li>GET /health</li><li>GET /v1/vehicles/{vin}</li><li>POST /v1/orders</li>
<li>GET /v1/orders/{id}</li><li>POST /v1/orders/{id}/advance</li><li>POST /v1/graphql</li></ul>
</body></html>"""


def make_handler(service: Service):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep test output clean
            pass

        def _send(self, status: int, body: dict | str,
                  content_type: str = "application/json") -> None:
            data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status: int, message: str) -> None:
            self._send(status, {"error": {"code": status, "message": message}})

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            try:
                return json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                raise OrderError("request body must be valid JSON")

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send(200, {"status": "ok"})
            elif parsed.path == "/":
                self._send(200, DASHBOARD_HTML, "text/html")
            elif parsed.path.startswith("/v1/vehicles/"):
                vin = parsed.path.split("/")[-1]
                doc = service.vehicles.get_vehicle(vin)
                if doc is None:
                    self._error(404, f"no vehicle listed for VIN {vin}")
                else:
                    self._send(200, doc)
            elif parsed.path.startswith("/v1/orders/"):
                order = service.orders.get_order(parsed.path.split("/")[-1])
                if order is None:
                    self._error(404, "unknown order")
                else:
                    self._send(200, order.to_dict())
            else:
                self._error(404, "not found")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                body = self._read_json()
                if parsed.path == "/v1/orders":
                    result, replayed = service.create_order(
                        body, self.headers.get("Idempotency-Key")
                    )
                    self._send(200 if replayed else 201, result)
                elif parsed.path.startswith("/v1/orders/") and parsed.path.endswith("/advance"):
                    order_id = parsed.path.split("/")[3]
                    to_state = body.get("to", "")
                    self._send(200, service.advance_order(order_id, to_state))
                elif parsed.path == "/v1/graphql":
                    self._send(200, {"data": service.graphql_query(body.get("query", ""))})
                else:
                    self._error(404, "not found")
            except OrderError as exc:
                self._error(400, str(exc))
            except Exception as exc:  # never leak a stack trace to clients
                self._error(500, f"internal error: {type(exc).__name__}")

    return Handler


def serve(service: Service | None = None, port: int = 8080) -> ThreadingHTTPServer:
    service = service or Service()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(service))
    return server


if __name__ == "__main__":
    print("Serving on http://127.0.0.1:8080")
    serve().serve_forever()
