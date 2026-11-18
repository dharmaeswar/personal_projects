"""Entry point: start the demo web service.

Usage:
    python run_service.py            # port from $PORT, default 8080
    PORT=9000 python run_service.py  # custom port
    LATENCY_MS=50 python run_service.py  # simulate ~50ms of latency
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from service.app import build_server  # noqa: E402


def main():
    port = int(os.environ.get("PORT", "8080"))
    server = build_server(port)
    print(
        f"platform-ops demo service listening on port {port} "
        "(synthetic traffic only)"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
