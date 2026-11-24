"""Enterprise AI Deployment Accelerator.

Takes a mid-market enterprise AI use case from prototype to production:
use-case intake and scoring, a retrieval-backed agent that answers from
the customer's own documents, a deterministic evaluation harness with
rubric graders, a production-readiness gate (reliability, latency, cost,
safety, governance, observability), and a reusable deployment playbook.

All data is synthetic and local. No real LLM or API calls: the agent is a
deterministic rule-based policy over a small document store, so every eval
is reproducible offline. A real model-backed agent plugs into the same
``plan / retrieve / answer / validate`` interfaces.
"""

from .intake import UseCase, rank_use_cases, score_use_case
from .retrieval import DocStore, Document
from .tools import Tool, ToolRegistry, build_enterprise_tools
from .agent import Agent, Answer
from .graders import Grade, grade_answer
from .harness import EvalCase, EvalResult, EvalSummary, run_eval
from .readiness import ReadinessGate, ReadinessReport, evaluate_readiness
from .playbook import generate_playbook

__all__ = [
    "UseCase", "rank_use_cases", "score_use_case",
    "DocStore", "Document",
    "Tool", "ToolRegistry", "build_enterprise_tools",
    "Agent", "Answer",
    "Grade", "grade_answer",
    "EvalCase", "EvalResult", "EvalSummary", "run_eval",
    "ReadinessGate", "ReadinessReport", "evaluate_readiness",
    "generate_playbook",
]
