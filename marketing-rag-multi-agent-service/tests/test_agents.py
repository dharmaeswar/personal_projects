from marketing_rag.agents import (AudienceAgent, BudgetAgent, ContentAgent,
                                  PlannerAgent, ValidatorAgent)
from marketing_rag.corpus import CAMPAIGNS, build_documents
from marketing_rag.retrieval import Retriever


def test_planner_budget_intent():
    plan = PlannerAgent().run("Where should we move budget from the weakest campaign?")
    assert "budget" in plan["intents"]
    assert plan["subtasks"][-1]["agent"] == "ValidatorAgent"


def test_planner_audience_intent():
    plan = PlannerAgent().run("Which audience segment should we target?")
    assert "audience" in plan["intents"]


def test_planner_unknown_question_defaults_to_performance():
    plan = PlannerAgent().run("Hello there")
    assert plan["intents"] == ["performance"]


def test_budget_best_and_worst_roi():
    stats = BudgetAgent().run("budget")
    assert stats["best_roi"]["id"] == "CMP-007"
    assert stats["best_roi"]["roi"] == 5.5
    assert stats["worst_roi"]["id"] == "CMP-005"
    assert stats["worst_roi"]["roi"] == 0.94
    assert stats["suggestion"] is not None
    assert "CMP-001" not in stats["suggestion"]  # suggestion names campaigns, not ids
    assert "Partner Co-Marketing" in stats["suggestion"]
    assert "Display Retargeting" in stats["suggestion"]


def test_budget_stats_arithmetic():
    stat = BudgetAgent.campaign_stats(CAMPAIGNS[4])  # CMP-005
    assert stat["cpa"] == 534.48
    assert stat["roi"] == 0.94


def test_audience_agent_matches_segment():
    retriever = Retriever(build_documents())
    retrieved = retriever.retrieve("small business owners segment")
    result = AudienceAgent().run("How large is the small business owners segment?", retrieved)
    ids = [s["id"] for s in result["segments"]]
    assert "SEG-003" in ids
    assert result["total_audience"] == sum(s["size"] for s in result["segments"])


def test_content_agent_picks_asset():
    retriever = Retriever(build_documents())
    retrieved = retriever.retrieve("spring email launch announcement")
    result = ContentAgent().run("What content asset fits the spring email launch?", retrieved)
    assert result["assets"]
    assert result["assets"][0]["id"] == "AST-002"


def test_validator_passes_retrieved_numbers():
    retriever = Retriever(build_documents())
    retrieved = retriever.retrieve("Spring Launch Email campaign")
    draft = "Spring Launch Email spent $42000 and returned 3.52x on spend."
    result = ValidatorAgent().run(draft, retrieved)
    assert result["passed"] is True
    assert result["unsupported"] == []


def test_validator_flags_invented_number():
    retriever = Retriever(build_documents())
    retrieved = retriever.retrieve("Spring Launch Email campaign")
    draft = "Spring Launch Email spent $42000 and drove 99999 conversions."
    result = ValidatorAgent().run(draft, retrieved)
    assert result["passed"] is False
    assert "99999" in result["unsupported"]


def test_validator_accepts_comma_formatting():
    retriever = Retriever(build_documents())
    retrieved = retriever.retrieve("mid-market ops leaders segment")
    draft = "Mid-market ops leaders has 18,400 contacts."
    result = ValidatorAgent().run(draft, retrieved)
    assert result["passed"] is True
