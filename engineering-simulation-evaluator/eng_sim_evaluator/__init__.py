"""Engineering simulation evaluator: benchmark AI-proposed engineering designs.

Modules: beam (cantilever deflection/stress), thermal (1D conduction),
calibration (recover Young's modulus from noisy synthetic measurements),
benchmark (score and rank candidate designs), metrics (MAE/RMSE/tolerance),
golden (frozen golden-reference outputs), provenance (evidence records),
guardrails (CI gates for agent-produced changes), mcp_server (MCP-style
tool layer that lets AI coding agents drive the simulators).
"""

from .beam import Beam
from .benchmark import Requirements
from .golden import GoldenCase, compare_golden, generate_golden
from .guardrails import GateResult, gate_change
from .metrics import mae, max_abs_error, rmse, within_tolerance
from .provenance import Provenance, record_provenance

__all__ = [
    "Beam",
    "GateResult",
    "GoldenCase",
    "Provenance",
    "Requirements",
    "compare_golden",
    "gate_change",
    "generate_golden",
    "mae",
    "max_abs_error",
    "record_provenance",
    "rmse",
    "within_tolerance",
]
