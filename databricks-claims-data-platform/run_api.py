"""Run the claims API server (default port 8080)."""
import sys

from claims_platform.api import run_server

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = run_server(port)
    print(f"claims API on http://127.0.0.1:{server.server_address[1]}")
    server.serve_forever()
