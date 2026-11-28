from genai_platform.gateway import Gateway, ModelBackend
from genai_platform.orchestration import GRAPH_NODES, run_graph
from genai_platform.rag import demo_knowledge_base


def test_graph_answers_covenant_question_with_citation():
    state = run_graph(
        "What is the leverage covenant limit for commercial loans?",
        demo_knowledge_base(),
        team="credit",
        use_case="covenant-qa",
    )
    assert "3.5x" in state.answer
    assert state.citations
    assert state.validation["grounded"] is True
    assert state.errors == []


def test_graph_plan_covers_all_nodes():
    state = run_graph(
        "What is the leverage covenant limit?",
        demo_knowledge_base(),
        team="credit",
        use_case="covenant-qa",
    )
    assert state.plan[0] == "retrieve"
    assert "generate" in state.plan
    assert "validate" in state.plan
    assert set(GRAPH_NODES) == {"plan", "retrieve", "generate", "validate"}


def test_graph_says_so_when_no_context():
    state = run_graph(
        "How do I bake sourdough bread?",
        demo_knowledge_base(),
        team="credit",
        use_case="covenant-qa",
    )
    assert "do not have supporting documentation" in state.answer
    assert any("no supporting context" in e for e in state.errors)


def test_graph_with_gateway_records_a_metered_call():
    gateway = Gateway()
    gateway.register(ModelBackend("amazon.titan-text-premier-v1:0"))
    run_graph(
        "What is the leverage covenant limit?",
        demo_knowledge_base(),
        team="credit",
        use_case="covenant-qa",
        gateway=gateway,
    )
    assert len(gateway.usage) == 1
    assert gateway.usage[0]["team"] == "credit"
