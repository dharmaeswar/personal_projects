"""Tiny sample REST API used as the system under test (stdlib only).

Endpoints:
- GET /health -> {"status": "ok"}
- GET /plans -> list of 2 plans; GET /plans/<id> -> one plan or 404
- GET /trades?limit=N&offset=M -> paged list of 5,000 deterministic trades
  plus {"total": 5000, "limit": N, "offset": M}; GET /trades/<id> -> one trade
  or 404. The trades endpoint is the high-volume data surface the volume
  tests exercise: pagination invariants, data invariants, and latency.
"""
import json
import random
from http.server import BaseHTTPRequestHandler, HTTPServer

PLANS = {
    1: {"id": 1, "name": "Basic", "price": 20.0, "data_gb": 5},
    2: {"id": 2, "name": "Plus", "price": 45.0, "data_gb": 25},
}

SYMBOLS = ["AAPL", "MSFT", "SPX", "NDX", "ES", "CL", "GC", "EURUSD"]
SIDES = ["BUY", "SELL"]
TRADE_COUNT = 5000
BASE_TS = 1764000000  # fixed epoch so the dataset is deterministic


def _build_trades():
    rng = random.Random(42)  # fixed seed: same 5,000 trades on every boot
    trades = []
    for i in range(1, TRADE_COUNT + 1):
        trades.append({
            "id": i,
            "symbol": rng.choice(SYMBOLS),
            "side": rng.choice(SIDES),
            "price": round(rng.uniform(10.0, 5000.0), 2),
            "qty": rng.randint(1, 1000),
            "ts": BASE_TS + i,
        })
    return trades


TRADES = _build_trades()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        elif self.path == "/plans":
            self._send(200, {"plans": list(PLANS.values())})
        elif self.path.startswith("/plans/"):
            try:
                plan = PLANS[int(self.path.split("/")[-1])]
            except (ValueError, KeyError):
                self._send(404, {"error": "plan not found"})
            else:
                self._send(200, plan)
        elif self.path == "/trades" or self.path.startswith("/trades?"):
            self._handle_trades_list()
        elif self.path.startswith("/trades/"):
            try:
                trade_id = int(self.path.split("/")[-1])
            except ValueError:
                self._send(404, {"error": "trade not found"})
                return
            if 1 <= trade_id <= TRADE_COUNT:
                self._send(200, TRADES[trade_id - 1])
            else:
                self._send(404, {"error": "trade not found"})
        else:
            self._send(404, {"error": "not found"})

    def _handle_trades_list(self):
        from urllib.parse import parse_qs, urlparse

        query = parse_qs(urlparse(self.path).query)
        try:
            limit = int(query.get("limit", ["100"])[0])
            offset = int(query.get("offset", ["0"])[0])
        except ValueError:
            self._send(400, {"error": "limit and offset must be integers"})
            return
        if limit < 1 or limit > 1000 or offset < 0:
            self._send(400, {"error": "limit must be 1-1000 and offset >= 0"})
            return
        page = TRADES[offset:offset + limit]
        self._send(200, {"trades": page, "total": TRADE_COUNT,
                         "limit": limit, "offset": offset})

    def log_message(self, *args):
        pass


def run(port=8765):
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    run()
