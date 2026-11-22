"""Tests for groundedness / hallucination detection."""
from genai_validation.candidate import CandidateModel
from genai_validation.data import CASES
from genai_validation.groundedness import groundedness, hallucination_rate

MODEL = CandidateModel()


def test_clean_explanation_fully_grounded():
    for case in CASES:
        out = MODEL.generate(case, seed=0)
        result = groundedness(out["explanation"], case["facts"])
        assert result["score"] == 1.0, (case["case_id"], result)
        assert not result["hallucination"]


def test_hallucinated_apr_is_flagged():
    case = CASES[0]
    out = MODEL.generate(case, seed=3)
    result = groundedness(out["explanation"], case["facts"])
    assert result["hallucination"]
    assert result["score"] < 1.0
    assert result["hallucinated"]


def test_hallucination_rate_counts_flagged_cases():
    results = [groundedness(MODEL.generate(c, seed=3)["explanation"], c["facts"])
               for c in CASES]
    rate = hallucination_rate(results)
    assert rate["cases"] == len(CASES)
    assert rate["flagged"] == len(CASES)
    assert rate["rate"] == 1.0


def test_clean_run_has_zero_hallucination_rate():
    results = [groundedness(MODEL.generate(c, seed=0)["explanation"], c["facts"])
               for c in CASES]
    assert hallucination_rate(results)["rate"] == 0.0
