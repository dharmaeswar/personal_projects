"""Investment research AI assistant: grounded RAG Q&A over research notes."""

from .qa import ResearchAssistant, Answer
from .evaluate import evaluate, EVAL_CASES

__all__ = ["ResearchAssistant", "Answer", "evaluate", "EVAL_CASES"]
