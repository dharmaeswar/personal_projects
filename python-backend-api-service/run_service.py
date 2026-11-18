"""Run the payments API service locally.

Usage:
    python run_service.py            # listens on http://127.0.0.1:8000
    python run_service.py 9000       # custom port
"""

import sys

from payments_api.app import run

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run(port)
