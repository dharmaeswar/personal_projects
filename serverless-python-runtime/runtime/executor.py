"""Executor: routes invocations to a small pool of warm workers.

The executor keeps one worker per (handler, function) pair up to the
configured concurrency limit, so repeat traffic for the same function reuses
a warm process and skips the import-time cold start. It records every
invocation in the shared Metrics store and raises when the pool is full
instead of queueing without bound.
"""

from .config import RuntimeConfig
from .observability import Metrics
from .worker import Worker


class Executor:
    """Dispatch invocations across a bounded pool of warm workers."""

    def __init__(self, config: RuntimeConfig | None = None):
        self.config = config or RuntimeConfig()
        self.config.validate()
        self.metrics = Metrics()
        self._workers: dict[tuple[str, str], Worker] = {}

    @property
    def pool_size(self) -> int:
        return len(self._workers)

    def invoke(self, handler_path: str, function: str, event: dict) -> dict:
        """Invoke a handler, reusing a warm worker when one exists."""
        key = (handler_path, function)
        worker = self._workers.get(key)
        if worker is None:
            if len(self._workers) >= self.config.max_concurrency:
                raise RuntimeError(
                    f"concurrency limit reached ({self.config.max_concurrency} "
                    "workers); refusing new worker"
                )
            worker = Worker()
            self._workers[key] = worker
        response = worker.invoke(
            handler_path, function, event, timeout_s=self.config.timeout_s
        )
        self.metrics.record(
            total_ms=response.get("total_ms", 0.0),
            cold=bool(response.get("cold")),
            ok=bool(response.get("ok")),
        )
        return response

    def shutdown(self) -> None:
        """Stop every worker in the pool."""
        for worker in self._workers.values():
            worker.stop()
        self._workers.clear()

    def __enter__(self) -> "Executor":
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown()
