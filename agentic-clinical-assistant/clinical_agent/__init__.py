"""Agentic Clinical Assistant package."""

from .agent import Agent, MAX_STEPS
from .audit import AuditLog
from .evals import EVAL_CASES, run_evals
from .phi import contains_phi, redact
from .pipeline import Pipeline, build_features, validate_record
from .retrieval import search
from .vector_store import FeatureStore, VectorStore, cosine, embed
from .rwd import (build_cohort, data_quality, generate_claims,
                 patient_journey, treatment_patterns, utilization_summary)
from .tools import ToolError, ToolServer

__all__ = [
    "Agent",
    "AuditLog",
    "EVAL_CASES",
    "MAX_STEPS",
    "FeatureStore",
    "Pipeline",
    "ToolError",
    "ToolServer",
    "VectorStore",
    "build_features",
    "contains_phi",
    "cosine",
    "embed",
    "redact",
    "run_evals",
    "search",
    "validate_record",
    "build_cohort",
    "data_quality",
    "generate_claims",
    "patient_journey",
    "treatment_patterns",
    "utilization_summary",
]
