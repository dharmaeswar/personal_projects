"""Routing across model backends.

Each model has one or more backends (GPU fleet endpoints). The router
picks the healthy backend with the most capacity headroom (lowest
in-flight / capacity ratio, tie-broken by lowest observed latency) and
fails over when a backend is down or saturated.
"""

import threading


class Backend:
    def __init__(self, backend_id, model, base_latency_ms, capacity):
        self.backend_id = backend_id
        self.model = model
        self.base_latency_ms = float(base_latency_ms)
        self.capacity = int(capacity)
        self.in_flight = 0
        self.healthy = True
        self._lock = threading.Lock()

    def headroom(self):
        """Free capacity as a fraction of total capacity (0..1)."""
        if self.capacity <= 0:
            return 0.0
        return max(0.0, (self.capacity - self.in_flight) / self.capacity)

    def acquire(self):
        with self._lock:
            if not self.healthy or self.in_flight >= self.capacity:
                return False
            self.in_flight += 1
            return True

    def release(self):
        with self._lock:
            self.in_flight = max(0, self.in_flight - 1)


class ModelRegistry:
    def __init__(self):
        self._backends = {}  # model -> [Backend]

    def register(self, backend):
        self._backends.setdefault(backend.model, []).append(backend)

    def models(self):
        return sorted(self._backends)

    def backends_for(self, model):
        return list(self._backends.get(model, []))


class Router:
    def __init__(self, registry):
        self.registry = registry

    def route(self, model):
        """Pick the best backend for `model`, or return (None, reason)."""
        backends = self.registry.backends_for(model)
        if not backends:
            return None, "unknown_model"
        candidates = [b for b in backends if b.healthy and b.in_flight < b.capacity]
        if not candidates:
            return None, "no_capacity"
        # Most headroom first, then lowest latency.
        candidates.sort(key=lambda b: (-b.headroom(), b.base_latency_ms))
        for backend in candidates:
            if backend.acquire():
                return backend, "ok"
        return None, "no_capacity"
