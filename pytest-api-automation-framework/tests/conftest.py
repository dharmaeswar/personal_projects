import threading
import time
import urllib.request

import pytest

from sample_api.server import run

PORT = 8765
BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="session", autouse=True)
def api_server():
    thread = threading.Thread(target=run, kwargs={"port": PORT}, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=1) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.1)
    yield BASE
