"""Start the public website platform API on :8000."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from website_platform.app import create_server

if __name__ == "__main__":
    server = create_server(port=8000)
    print("Public website platform API on http://127.0.0.1:8000")
    server.serve_forever()
