"""Tests for verdicts, risk scores, reviewer suggestions, and reports."""

from changereview.diffparse import parse_diff
from changereview.report import to_json, to_markdown
from changereview.review import review_change, risk_score, suggest_reviewers
from changereview.signals import analyze_change
from test_signals import CLEAN_DIFF, EVAL_DIFF, TODO_DIFF


def test_block_verdict_on_secret():
    review = review_change(analyze_change(parse_diff(EVAL_DIFF)))
    assert review.verdict == "BLOCK"
    assert review.risk_score >= 40
    assert any("Blocking" in reason for reason in review.reasons)


def test_needs_review_on_warning():
    review = review_change(analyze_change(parse_diff(TODO_DIFF)))
    assert review.verdict == "NEEDS_REVIEW"
    assert review.risk_score == 20  # 10 warning + 10 no-tests


def test_approve_on_clean_change():
    review = review_change(analyze_change(parse_diff(CLEAN_DIFF)))
    assert review.verdict == "APPROVE"
    assert review.risk_score == 0
    assert review.reasons == []


def test_low_coverage_forces_needs_review():
    coverage = {"src/app.py": {1}, "tests/test_app.py": {1}}
    review = review_change(analyze_change(parse_diff(CLEAN_DIFF), coverage=coverage))
    assert review.verdict == "NEEDS_REVIEW"
    assert any("coverage" in reason for reason in review.reasons)


def test_risk_score_is_capped_at_100():
    signals = analyze_change(parse_diff(EVAL_DIFF))
    assert risk_score(signals) <= 100


def test_reviewer_suggestion_uses_longest_prefix():
    owners = {
        "src/": ["general-team"],
        "src/payments/": ["payments-team", "alice"],
    }
    reviewers = suggest_reviewers(["src/payments/charge.py", "src/util.py"], owners)
    assert reviewers == ["payments-team", "alice", "general-team"]


def test_no_owners_means_no_reviewers():
    assert suggest_reviewers(["src/app.py"], None) == []
    assert suggest_reviewers(["src/app.py"], {}) == []


def test_markdown_report_contains_verdict_and_reasons():
    review = review_change(analyze_change(parse_diff(TODO_DIFF)))
    text = to_markdown(review)
    assert "# Change Review — NEEDS_REVIEW" in text
    assert "Risk score:" in text
    assert "TODO" in text


def test_json_report_round_trips():
    import json

    review = review_change(analyze_change(parse_diff(CLEAN_DIFF)))
    payload = json.loads(to_json(review))
    assert payload["verdict"] == "APPROVE"
    assert payload["change"]["lines_added"] == 2
    assert payload["findings"] == []
