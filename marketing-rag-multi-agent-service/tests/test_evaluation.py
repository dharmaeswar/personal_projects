from marketing_rag.evaluation import EVAL_CASES, run_evaluation
from marketing_rag.service import MarketingRagService


def test_eval_cases_cover_kinds():
    assert len(EVAL_CASES) == 8
    assert all(c["expected"] for c in EVAL_CASES)


def test_evaluation_report_shape():
    report = run_evaluation(MarketingRagService())
    assert report["cases"] == 8
    assert 0.0 <= report["mean_precision_at_3"] <= 1.0
    assert 0.0 <= report["citation_coverage"] <= 1.0
    assert report["faithfulness"] == 1.0  # every answer passes the validator
    assert len(report["results"]) == 8


def test_evaluation_results_have_expected_docs():
    report = run_evaluation(MarketingRagService())
    by_question = {r["question"]: r for r in report["results"]}
    assert by_question["How large is the small business owners segment?"]["covered_in_top5"] is True
    assert by_question["What is the CPA of the Display Retargeting campaign?"]["covered_in_top5"] is True
