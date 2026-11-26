"""Runtime configuration for the serverless Python runtime.

A RuntimeConfig is the single place a service owner declares the execution
envelope for a function: how much memory it may use, how long one invocation
may run, how many workers may run at once, and how large its deployment
bundle may be. Invalid envelopes are rejected up front instead of failing
mid-invocation.
"""

from dataclasses import dataclass


@dataclass
class RuntimeConfig:
    """Execution envelope for one serverless Python function."""

    memory_mb: int = 512
    timeout_s: int = 30
    max_concurrency: int = 10
    bundle_budget_mb: int = 250
    python_version: str = "3.12"

    def validate(self) -> None:
        """Raise ValueError on any out-of-range setting."""
        if not 128 <= self.memory_mb <= 10240:
            raise ValueError(f"memory_mb must be 128-10240, got {self.memory_mb}")
        if not 1 <= self.timeout_s <= 900:
            raise ValueError(f"timeout_s must be 1-900, got {self.timeout_s}")
        if not 1 <= self.max_concurrency <= 1000:
            raise ValueError(
                f"max_concurrency must be 1-1000, got {self.max_concurrency}"
            )
        if not 1 <= self.bundle_budget_mb <= 1024:
            raise ValueError(
                f"bundle_budget_mb must be 1-1024, got {self.bundle_budget_mb}"
            )
        if self.python_version not in ("3.11", "3.12", "3.13"):
            raise ValueError(
                f"unsupported python_version {self.python_version!r}"
            )

    def as_dict(self) -> dict:
        return {
            "memory_mb": self.memory_mb,
            "timeout_s": self.timeout_s,
            "max_concurrency": self.max_concurrency,
            "bundle_budget_mb": self.bundle_budget_mb,
            "python_version": self.python_version,
        }
