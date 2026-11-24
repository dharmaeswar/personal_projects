from bank_rag.evaluate import EVAL_CASES, run_evaluation, score_case
from bank_rag.pipeline import run_question


def test_eval_set_has_eight_cases():
    assert len(EVAL_CASES) == 8


def test_full_evaluation_passes():
    evaluation = run_evaluation()
    assert evaluation["accuracy"] == 1.0
    assert evaluation["groundedness"] == 1.0
    assert evaluation["citation_coverage"] == 1.0


def test_score_case_rejects_wrong_number():
    result = run_question("What is Northgate Logistics Group's leverage ratio?")
    passed, _ = score_case(result, {"expected_number": 9.9, "tolerance": 0.01})
    assert passed is False
