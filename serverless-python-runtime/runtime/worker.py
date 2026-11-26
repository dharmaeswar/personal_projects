"""Worker: one long-lived agent process owned by the executor.

A Worker starts the agent subprocess, sends it one JSON-lines invocation at
a time, and reads the response with a timeout. A timeout kills the worker
(the handler may be stuck), and a dead worker is never reused. Cold starts
happen only on the first invocation of a handler in a worker; later
invocations on the same worker are warm.
"""

import json
import select
import subprocess
import sys


class WorkerTimeout(TimeoutError):
    """Raised when a handler does not answer within the timeout."""


class Worker:
    """A single agent subprocess that executes handler invocations."""

    def __init__(self, python: str = sys.executable):
        self._proc = subprocess.Popen(
            [python, "-m", "runtime.agent"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self.invocations = 0
        self.alive = True

    @property
    def pid(self) -> int | None:
        return self._proc.pid

    def invoke(
        self, handler_path: str, function: str, event: dict, timeout_s: int = 30
    ) -> dict:
        """Run one invocation; return the agent's response dict."""
        if not self.alive:
            raise RuntimeError("worker is dead")
        request = {
            "handler_path": handler_path,
            "function": function,
            "event": event,
        }
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._proc.stdin.write(json.dumps(request) + "\n")
        self._proc.stdin.flush()
        ready, _, _ = select.select([self._proc.stdout], [], [], timeout_s)
        if not ready:
            self._kill()
            raise WorkerTimeout(
                f"handler {function} in {handler_path} timed out "
                f"after {timeout_s}s"
            )
        line = self._proc.stdout.readline()
        if not line:
            self._kill()
            raise RuntimeError("worker agent exited without a response")
        self.invocations += 1
        return json.loads(line)

    def _kill(self) -> None:
        self.alive = False
        try:
            self._proc.kill()
        except OSError:
            pass
        self._proc.wait()

    def stop(self) -> None:
        """Shut the agent down cleanly (or kill it if it ignores EOF)."""
        if not self.alive:
            return
        self.alive = False
        try:
            assert self._proc.stdin is not None
            self._proc.stdin.close()
            self._proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError, BrokenPipeError):
            self._kill()

    def __enter__(self) -> "Worker":
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
