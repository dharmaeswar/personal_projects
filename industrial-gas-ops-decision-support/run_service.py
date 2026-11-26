"""Start the gas-ops decision-support service on http://127.0.0.1:8000."""

import sys

from gas_ops.api import run

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run(port=port)
