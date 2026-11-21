"""Prometheus-format metrics for the Freight Ops service (demo).

Counters only: requests by method/path/status and shipments by status.
This is the same text exposition format Prometheus scrapes; the service
does not claim a production Prometheus/Grafana deployment.
"""

import threading


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._requests = {}
        self._shipments_by_status = {}

    def record_request(self, method, path, status):
        key = (method, path, str(status))
        with self._lock:
            self._requests[key] = self._requests.get(key, 0) + 1

    def set_shipments(self, by_status):
        with self._lock:
            self._shipments_by_status = dict(by_status)

    def render(self):
        lines = [
            "# HELP freight_ops_requests_total Total HTTP requests by method, path and status.",
            "# TYPE freight_ops_requests_total counter",
        ]
        with self._lock:
            requests = sorted(self._requests.items())
            shipments = sorted(self._shipments_by_status.items())
        for (method, path, status), count in requests:
            lines.append(
                f'freight_ops_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}'
            )
        lines.append("# HELP freight_ops_shipments Shipments by status.")
        lines.append("# TYPE freight_ops_shipments gauge")
        for status, count in shipments:
            lines.append(f'freight_ops_shipments{{status="{status}"}} {count}')
        return "\n".join(lines) + "\n"
