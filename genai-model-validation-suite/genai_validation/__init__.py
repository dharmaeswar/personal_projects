"""GenAI model validation suite: hallucination, reliability, benchmarking,
sensitivity, drift and explainability checks for LLM decision support.
"""
from .harness import run_validation

__all__ = ["run_validation"]
