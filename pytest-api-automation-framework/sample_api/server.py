"""Tiny sample REST API used as the system under test (stdlib only)."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

PLANS = {
    1: {"id": 1, "name": "Basic", "price": 20.0, "data_gb": 5},
    2: {"id": 2, "name": "Plus", "price": 45.0, "data_gb": 25},
}


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
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *args):
        pass


def run(port=8765):
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    run()
