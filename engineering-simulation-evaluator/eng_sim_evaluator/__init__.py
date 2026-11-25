"""Engineering simulation evaluator: benchmark AI-proposed engineering designs.

Modules: beam (cantilever deflection/stress), thermal (1D conduction),
calibration (recover Young's modulus from noisy synthetic measurements),
benchmark (score and rank candidate designs), metrics (MAE/RMSE/tolerance),
golden (frozen golden-reference outputs), provenance (evidence records),
guardrails (CI gates for agent-produced changes), mcp_server (MCP-style
tool layer that lets AI coding agents drive the simulators), energy_data
(synthetic drilling telemetry, data dictionary, cleaning and EDA),
energy_model (feature engineering, OLS and random-forest ROP models,
holdout validation, sensitivity, model card), deployment (JSON model
artifact, artifact prediction, deployment checklist).
"""

from .beam import Beam
from .benchmark import Requirements
from .deployment import (
    deployment_checklist,
    export_model_artifact,
    predict_from_artifact,
)
from .energy_data import (
    DATA_DICTIONARY,
    analytic_rop,
    clean_and_validate,
    eda_summary,
    generate_drilling_data,
)
from .energy_model import (
    FEATURES,
    OlsModel,
    build_features,
    model_card,
    validate_models,
)
from .golden import GoldenCase, compare_golden, generate_golden
from .guardrails import GateResult, gate_change
from .metrics import mae, max_abs_error, rmse, within_tolerance
from .provenance import Provenance, record_provenance

__all__ = [
    "Beam",
    "DATA_DICTIONARY",
    "FEATURES",
    "GateResult",
    "GoldenCase",
    "OlsModel",
    "Provenance",
    "Requirements",
    "analytic_rop",
    "build_features",
    "clean_and_validate",
    "compare_golden",
    "deployment_checklist",
    "eda_summary",
    "export_model_artifact",
    "gate_change",
    "generate_drilling_data",
    "generate_golden",
    "mae",
    "max_abs_error",
    "model_card",
    "predict_from_artifact",
    "record_provenance",
    "rmse",
    "validate_models",
    "within_tolerance",
]
