from bank_rag.agents import Analyst, Planner, Validator
from bank_rag.context import build_context
from bank_rag.corpus import build_corpus
from bank_rag.pipeline import run_question
from bank_rag.retrieval import TextIndex, hybrid_retrieve

DOCS = build_corpus()


def _context_for(question):
    retrieved = hybrid_retrieve(question, DOCS, TextIndex(DOCS))
    return build_context(retrieved)


def test_planner_splits_ratio_and_covenant_work():
    plan = Planner().plan("Is BlueRock Packaging Co in compliance with its leverage covenant?")
    assert "numeric-lookup" in plan["subtasks"]
    assert "covenant-check" in plan["subtasks"]
    assert plan["borrower"] == "BlueRock Packaging Co"


def test_analyst_leverage_ratio():
    question = "What is Northgate Logistics Group's leverage ratio?"
    result = Analyst().answer(question, _context_for(question), Planner().plan(question))
    assert "3.50x" in result["answer"]
    assert result["computed"]["leverage"] == 3.5


def test_analyst_covenant_breach():
    question = "Is BlueRock Packaging Co in compliance with its leverage covenant?"
    result = Analyst().answer(question, _context_for(question), Planner().plan(question))
    assert "in breach" in result["answer"]
    assert result["computed"]["leverage_ok"] is False


def test_analyst_highest_margin():
    question = "Which borrower has the highest EBITDA margin?"
    result = Analyst().answer(question, _context_for(question), Planner().plan(question))
    assert "BlueRock Packaging Co" in result["answer"]
    assert "15.00%" in result["answer"]


def test_analyst_memo_answer():
    question = "What does the credit memo say about Summit Ridge Manufacturing's supply-chain risk?"
    result = Analyst().answer(question, _context_for(question), Planner().plan(question))
    assert "single-source supplier" in result["answer"]


def test_validator_passes_grounded_answer():
    result = run_question("What is Northgate Logistics Group's leverage ratio?")
    assert result["validation"]["verdict"] == "PASS"


def test_validator_flags_ungrounded_number():
    context = _context_for("What is Northgate Logistics Group's leverage ratio?")
    check = Validator().validate(
        "Northgate Logistics Group leverage is 9.99x.",
        context, {"leverage": 9.99}, {"borrower": "Northgate Logistics Group"})
    assert check["verdict"] == "FAIL"
    assert any("9.99" in f for f in check["findings"])


def test_validator_flags_wrong_covenant_verdict():
    context = _context_for("Is BlueRock Packaging Co in compliance with its leverage covenant?")
    check = Validator().validate(
        "BlueRock Packaging Co is in compliance: leverage 4.00x against a maximum of 3.5x.",
        context, {}, {"borrower": "BlueRock Packaging Co"})
    assert check["verdict"] == "FAIL"
    assert any("verdict wrong" in f for f in check["findings"])


def test_pipeline_end_to_end():
    result = run_question("What is Summit Ridge Manufacturing's EBITDA margin?")
    assert "12.50%" in result["answer"]
    assert result["validation"]["verdict"] == "PASS"
    assert result["citations"]
