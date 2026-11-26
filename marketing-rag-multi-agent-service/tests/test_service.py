from marketing_rag.service import MarketingRagService


def test_ask_budget_question():
    result = MarketingRagService().ask("Which campaign has the best return on spend?")
    assert "Partner Co-Marketing" in result["answer"]
    assert "5.50x" in result["answer"]
    assert result["validation"]["passed"] is True
    assert result["validation"]["unsupported"] == []
    assert result["citations"]
    assert result["citations"][0]["id"] == "CMP-007"
    assert "budget" in result["intents"] or "performance" in result["intents"]


def test_ask_audience_question():
    result = MarketingRagService().ask("How large is the small business owners segment?")
    assert "Small business owners" in result["answer"]
    assert "42,300" in result["answer"]
    assert result["validation"]["passed"] is True


def test_ask_content_question():
    result = MarketingRagService().ask("What content asset fits the spring email launch?")
    assert "Spring Launch Announcement Email" in result["answer"]
    assert result["validation"]["passed"] is True


def test_ask_empty_question():
    result = MarketingRagService().ask("   ")
    assert "Please ask" in result["answer"]
    assert result["citations"] == []


def test_ask_derived_values_marked():
    result = MarketingRagService().ask("Where should we move budget from the weakest campaign?")
    assert result["derived"]["budget_suggestion"] is not None
    assert "Derived by arithmetic" in result["derived"]["note"]
    assert result["derived"]["total_spend"] == sum(
        c["spend"] for c in
        __import__("marketing_rag.corpus", fromlist=["CAMPAIGNS"]).CAMPAIGNS)


def test_ask_citations_have_scores():
    result = MarketingRagService().ask("webinar lead follow-up")
    assert all(0 < c["score"] <= 1 for c in result["citations"])
    assert all(c["id"] for c in result["citations"])
