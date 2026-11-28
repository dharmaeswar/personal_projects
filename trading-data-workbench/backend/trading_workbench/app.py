"""HTTP API for the trading data workbench (Python standard library only).

Endpoints:
    GET  /health
    GET  /metrics
    GET  /api/instruments
    GET  /api/instruments/<symbol>
    GET  /api/quotes?symbol=<symbol>&limit=<n>
    GET  /api/orders
    POST /api/orders            (Idempotency-Key header supported)
    GET  /api/orders/<id>
    GET  /api/positions
    GET  /api/data-quality

Runs on ThreadingHTTPServer; the store lock serialises order writes so
concurrent requests cannot oversell a position.
"""

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .store import Store
from .validation import check_quote_series, validate_order_payload, validate_quote

STORE = Store()
STARTED_AT = time.time()
REQUEST_COUNTS = {}
COUNTS_LOCK = threading.Lock()


def _json(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _text(handler, status, body, content_type="text/plain"):
    raw = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def _read_body(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return None, "empty request body"
    if length > 65536:
        return None, "request body too large"
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8")), None
    except (ValueError, UnicodeDecodeError):
        return None, "request body is not valid JSON"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep test output clean
        pass

    def _count(self, path):
        with COUNTS_LOCK:
            REQUEST_COUNTS[path] = REQUEST_COUNTS.get(path, 0) + 1

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        self._count(path)
        query = parse_qs(parsed.query)

        if path == "/health":
            return _json(self, 200, {"status": "ok"})
        if path == "/metrics":
            lines = [
                "# Trading data workbench metrics",
                f"uptime_seconds {time.time() - STARTED_AT:.1f}",
            ]
            with COUNTS_LOCK:
                for key in sorted(REQUEST_COUNTS):
                    lines.append(f'http_requests_total{{path="{key}"}} {REQUEST_COUNTS[key]}')
            return _text(self, 200, "\n".join(lines) + "\n")
        if path == "/api/instruments":
            return _json(self, 200, {"instruments": STORE.list_instruments()})
        if path == "/api/quotes":
            symbol = (query.get("symbol") or [None])[0]
            if not symbol:
                return _json(self, 400, {"error": "query param symbol is required"})
            if STORE.get_instrument(symbol) is None:
                return _json(self, 404, {"error": f"unknown symbol: {symbol}"})
            try:
                limit = int((query.get("limit") or ["60"])[0])
            except ValueError:
                return _json(self, 400, {"error": "limit must be an integer"})
            if limit < 1 or limit > 500:
                return _json(self, 400, {"error": "limit must be between 1 and 500"})
            return _json(self, 200, {"symbol": symbol.upper(), "quotes": STORE.quotes(symbol, limit)})
        if path == "/api/orders":
            return _json(self, 200, {"orders": STORE.list_orders()})
        if path == "/api/positions":
            return _json(self, 200, {"positions": STORE.positions()})
        if path == "/api/data-quality":
            report = []
            for inst in STORE.list_instruments():
                rows = STORE.quotes(inst["symbol"])
                issues = []
                for row in rows:
                    issues.extend(validate_quote(row))
                issues.extend(check_quote_series(rows))
                report.append({
                    "symbol": inst["symbol"],
                    "rows_checked": len(rows),
                    "issues": issues,
                })
            return _json(self, 200, {"report": report})

        match = re.fullmatch(r"/api/instruments/([A-Za-z]+)", path)
        if match:
            inst = STORE.get_instrument(match.group(1))
            if inst is None:
                return _json(self, 404, {"error": f"unknown symbol: {match.group(1)}"})
            quote = STORE.latest_quote(inst["symbol"])
            return _json(self, 200, {**inst, "latest_quote": quote})

        match = re.fullmatch(r"/api/orders/(\d+)", path)
        if match:
            order = STORE.get_order(int(match.group(1)))
            if order is None:
                return _json(self, 404, {"error": f"unknown order: {match.group(1)}"})
            return _json(self, 200, order)

        return _json(self, 404, {"error": f"unknown route: {path}"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        self._count(path)
        if path != "/api/orders":
            return _json(self, 404, {"error": f"unknown route: {path}"})
        payload, error = _read_body(self)
        if error:
            return _json(self, 400, {"error": error})
        errors, cleaned = validate_order_payload(payload, STORE)
        if errors:
            return _json(self, 400, {"error": "; ".join(errors)})
        key = self.headers.get("Idempotency-Key")
        try:
            order, replayed = STORE.place_order(
                cleaned["symbol"], cleaned["side"], cleaned["qty"],
                cleaned["order_type"], cleaned["limit_price"], key,
            )
        except ValueError as exc:
            return _json(self, 422, {"error": str(exc)})
        return _json(self, 200 if replayed else 201, order)


def run(port=8000):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Trading data workbench listening on http://127.0.0.1:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    run()
