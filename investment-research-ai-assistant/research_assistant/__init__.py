"""Investment research AI assistant: grounded RAG Q&A over research notes."""

from .kpi import (
    backtest_kpi_signal,
    dashboard_summary,
    detect_inflections,
    forecast_kpi,
    kpi_report,
    kpi_signal,
    load_kpi_panel,
)
from .qa import ResearchAssistant, Answer
from .evaluate import evaluate, EVAL_CASES

__all__ = [
    "ResearchAssistant", "Answer", "evaluate", "EVAL_CASES",
    "load_kpi_panel", "detect_inflections", "forecast_kpi", "kpi_signal",
    "backtest_kpi_signal", "dashboard_summary", "kpi_report",
]
