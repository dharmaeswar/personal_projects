"""Serverless Python runtime: packaging, warm-worker execution, and observability.

Standard library only at runtime. The runtime models what a Languages and
Runtimes team does for serverless Python: take a handler plus a dependency
manifest, build a size-budgeted deployment bundle with precompiled bytecode,
then execute it on a pool of warm worker processes while measuring cold
starts, latency, and resource use.
"""

__all__ = ["config", "packaging", "worker", "executor", "observability"]
