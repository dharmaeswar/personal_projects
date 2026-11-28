"""Run the trading data workbench API locally.

Usage:
    python run_service.py            # listens on http://127.0.0.1:8000
    python run_service.py 9000       # custom port
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from trading_workbench.app import run

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run(port)
