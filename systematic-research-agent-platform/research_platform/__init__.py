"""Systematic Research Agent Platform: multi-agent research over a knowledge
layer of code, research notes, and datasets, with trajectory evaluation."""

from .orchestrator import ResearchRun
from .evaluate import run_evaluation, regression_report

__all__ = ["ResearchRun", "run_evaluation", "regression_report"]
