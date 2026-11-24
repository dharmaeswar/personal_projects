"""Support Quality & Coaching Evaluator."""

from .data import CASES, KB_ARTICLES, RUBRIC, SIMULATION_SCENARIOS, check_dataset
from .judge import JudgeResult, RuleBasedJudge
from .retrieval import KnowledgeRetriever, RetrievalHit
from .coaching import CoachingPlan, build_coaching_plan
from .simulation import SimulationSession, SimulationReport
from .evaluation import OfflineReport, compare_prompts, evaluate_offline

__all__ = [
    "CASES", "KB_ARTICLES", "RUBRIC", "SIMULATION_SCENARIOS",
    "check_dataset", "JudgeResult", "RuleBasedJudge",
    "KnowledgeRetriever", "RetrievalHit",
    "CoachingPlan", "build_coaching_plan",
    "SimulationSession", "SimulationReport",
    "OfflineReport", "compare_prompts", "evaluate_offline",
]
