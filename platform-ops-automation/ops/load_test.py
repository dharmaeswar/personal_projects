"""Stdlib-only load test for the Platform Ops Automation demo service.

Sends concurrent GET requests with urllib + threads and reports totals,
error rate, and p50/p95 latency. If the service is not reachable, it exits
non-zero with a clear error instead of crashing.

Usage:
    python ops/load_test.py [--url URL] [--requests N] [--concurrency N]
"""

import argparse
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, __file__.rsplit("/ops/", 1)[0])
from ops.log_analysis import p50, p95  # noqa: E402


def run_load_test(base_url, total_requests=100, concurrency=10):
    """Run the load test. Returns a summary dict.

    Raises ConnectionError if the service cannot be reached at all.
    """
    # Quick reachability check before spawning threads.
    try:
        with urllib.request.urlopen(base_url + "/health", timeout=5) as resp:
            resp.read()
    except Exception as exc:
        raise ConnectionError(
            f"service not reachable at {base_url} "
            f"(is it running? start it with: python run_service.py). "
            f"Underlying error: {exc}"
        ) from exc

    latencies = []
    errors = 0
    counter_lock = threading.Lock()
    next_index = {"value": 0}

    def worker():
        nonlocal errors
        while True:
            with counter_lock:
                if next_index["value"] >= total_requests:
                    return
                next_index["value"] += 1
            started = time.monotonic()
            try:
                with urllib.request.urlopen(base_url + "/", timeout=10) as resp:
                    resp.read()
                    status = resp.status
            except urllib.error.HTTPError as exc:
                status = exc.code
            except Exception:
                status = 0  # connection-level failure
            latency = time.monotonic() - started
            with counter_lock:
                latencies.append(latency)
                if status >= 500 or status == 0:
                    errors += 1

    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    started = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - started

    return {
        "total": len(latencies),
        "errors": errors,
        "error_rate": errors / len(latencies) if latencies else 1.0,
        "p50": p50(latencies),
        "p95": p95(latencies),
        "elapsed_seconds": round(elapsed, 2),
        "requests_per_second": round(len(latencies) / elapsed, 1) if elapsed else 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Load-test the demo service.")
    parser.add_argument("--url", default="http://127.0.0.1:8080",
                        help="base URL of the service")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    try:
        summary = run_load_test(args.url, args.requests, args.concurrency)
    except ConnectionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"total requests: {summary['total']}")
    print(f"errors: {summary['errors']} ({summary['error_rate']:.1%})")
    print(f"p50 latency: {summary['p50']:.3f}s")
    print(f"p95 latency: {summary['p95']:.3f}s")
    print(f"elapsed: {summary['elapsed_seconds']}s "
          f"({summary['requests_per_second']} req/s)")
    sys.exit(0 if summary["error_rate"] < 0.05 else 2)


if __name__ == "__main__":
    main()
