"""Run the Inventory Orchestration Service locally (default port 8000)."""

import os

from inventory_orchestration.app import run

if __name__ == "__main__":
    run(port=int(os.environ.get("PORT", "8000")))
