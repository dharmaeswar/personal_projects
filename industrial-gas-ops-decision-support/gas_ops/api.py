"""Full-stack service: REST API + single-page frontend for gas operations.

Standard-library only. The server seeds an in-memory SQLite store on
startup, serves the HTML dashboard at `/`, and exposes JSON endpoints
for inventory, forecasts, route planning and stockout simulation.
Run with `python run_service.py` (default http://127.0.0.1:8000).
"""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .data import CUSTOMERS, PLANTS, customer_by_id, generate_demand_history, plant_by_id
from .forecast import backtest, forecast
from .optimize import distance, plan_route
from .store import (
    get_customer_history,
    get_inventory,
    init_db,
    list_deliveries,
    record_delivery,
    seed,
)
from .simulate import safety_stock, simulate_demand

FRONTEND_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend.html")


def build_store():
    conn = init_db()
    seed(conn, PLANTS, CUSTOMERS, generate_demand_history())
    return conn


class Handler(BaseHTTPRequestHandler):
    conn = None  # set by make_server
    _request_lock = threading.Lock()  # one SQLite connection, one request at a time

    def handle_one_request(self):
        with self._request_lock:
            super().handle_one_request()

    def log_message(self, *args):  # keep test output clean
        pass

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, text):
        body = text.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        conn = self.conn
        if path == "/":
            with open(FRONTEND_PATH, encoding="utf-8") as fh:
                self._send_html(fh.read())
        elif path == "/health":
            self._send_json({"status": "ok"})
        elif path == "/api/dashboard":
            self._send_json(
                {
                    "plants": [
                        {"plant_id": p[0], "name": p[1], "product": p[2],
                         "daily_capacity_t": p[3]}
                        for p in PLANTS
                    ],
                    "customers": [
                        {"customer_id": c[0], "name": c[1], "product": c[2],
                         "base_demand_t": c[3]}
                        for c in CUSTOMERS
                    ],
                    "inventory": get_inventory(conn),
                    "deliveries": list_deliveries(conn),
                }
            )
        elif path == "/api/forecast":
            customer_id = query.get("customer", [None])[0]
            days = int(query.get("days", ["7"])[0])
            if customer_id is None:
                return self._send_json({"error": "customer is required"}, 400)
            try:
                series = get_customer_history(conn, customer_id)
            except Exception as exc:  # noqa: BLE001 - surface as a 400
                return self._send_json({"error": str(exc)}, 400)
            if not series:
                return self._send_json({"error": "unknown customer"}, 400)
            mape, naive = backtest(series)
            self._send_json(
                {
                    "customer": customer_id,
                    "forecast": forecast(series, days=days),
                    "backtest_mape_pct": mape,
                    "naive_mape_pct": naive,
                }
            )
        elif path == "/api/simulate":
            customer_id = query.get("customer", [None])[0]
            inventory = float(query.get("inventory", ["0"])[0])
            if customer_id is None:
                return self._send_json({"error": "customer is required"}, 400)
            series = get_customer_history(conn, customer_id)
            if not series:
                return self._send_json({"error": "unknown customer"}, 400)
            prob, mean, sd = simulate_demand(series, inventory)
            self._send_json(
                {
                    "customer": customer_id,
                    "inventory_t": inventory,
                    "stockout_probability": prob,
                    "mean_t": mean,
                    "sd_t": sd,
                    "safety_stock_95_t": safety_stock(series),
                }
            )
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/route":
            return self._send_json({"error": "not found"}, 404)
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            plant = plant_by_id(payload["plant"])
            cust_ids = payload.get("customers", [])
            if not cust_ids:
                return self._send_json({"error": "at least one customer is required"}, 400)
            points = []
            for cid in cust_ids:
                cust = customer_by_id(cid)
                if cust[2] != plant[2]:
                    return self._send_json(
                        {"error": f"{cid} uses {cust[2]}, plant makes {plant[2]}"}, 400
                    )
                points.append((cust[4], cust[5]))
            order_idx, dist_km, naive_km = plan_route((plant[4], plant[5]), points)
            order = [cust_ids[i] for i in order_idx]
            saved = round((naive_km - dist_km) / naive_km * 100, 1) if naive_km else 0.0
            # Persist the planned deliveries (day 0) for the dashboard.
            for cid in order:
                cust = customer_by_id(cid)
                record_delivery(
                    self.conn, plant[0], cid, cust[3],
                    distance((plant[4], plant[5]), (cust[4], cust[5])), 0,
                )
            self._send_json(
                {
                    "plant": plant[0],
                    "order": order,
                    "distance_km": dist_km,
                    "naive_km": naive_km,
                    "saved_pct": saved,
                }
            )
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            self._send_json({"error": str(exc)}, 400)


def make_server(host="127.0.0.1", port=0):
    Handler.conn = build_store()
    server = ThreadingHTTPServer((host, port), Handler)
    return server


def run(host="127.0.0.1", port=8000):
    server = make_server(host, port)
    print(f"Serving on http://{host}:{server.server_address[1]}")
    server.serve_forever()


if __name__ == "__main__":
    run()
