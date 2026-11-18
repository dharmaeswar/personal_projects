"""Subprocess-based CI step runner.

Runs one shell command per CI step (for example ``python -m pytest -q``)
with a timeout, captures stdout/stderr, and reports a pass/fail per
step. A step that times out or exits non-zero fails. This models the
"run the checks" part of a CI pipeline in plain Python; it is not a
CI server.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class StepResult:
    name: str
    command: str
    passed: bool
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False


def run_step(
    name: str,
    command: str,
    timeout_seconds: float = 120.0,
    cwd: str | None = None,
) -> StepResult:
    """Run ``command`` in a shell and return its captured result."""
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=cwd,
        )
        return StepResult(
            name=name,
            command=command,
            passed=proc.returncode == 0,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
    except subprocess.TimeoutExpired as exc:
        return StepResult(
            name=name,
            command=command,
            passed=False,
            returncode=None,
            stdout=exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or ""),
            stderr=exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or ""),
            timed_out=True,
        )


def run_steps(steps: list[dict], timeout_seconds: float = 120.0) -> list[StepResult]:
    """Run steps in order. Stops at the first failure, like a CI job
    that fails fast. Each step is ``{"name": ..., "command": ...}``."""
    results: list[StepResult] = []
    for step in steps:
        result = run_step(
            step["name"], step["command"],
            timeout_seconds=timeout_seconds, cwd=step.get("cwd"),
        )
        results.append(result)
        if not result.passed:
            break
    return results
