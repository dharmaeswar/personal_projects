"""Tests for the evidence-grounded draft evaluation module."""

from agent_eval.evidence import (DRAFT_SCENARIOS, DraftClaim,
                                 DraftEvaluator, EvidenceStore,
                                 ReviewFeedback, build_store)


def _evaluator(role="drafter"):
    return DraftEvaluator(build_store(), role=role)


def test_clean_draft_fully_supported():
    result = _evaluator().evaluate(DRAFT_SCENARIOS["draft-clean"])
    assert result["total"] == 2
    assert result["supported"] == 2
    assert result["groundedness"] == 1.0


def test_stale_version_flagged():
    result = _evaluator().evaluate(DRAFT_SCENARIOS["draft-stale"])
    assert result["verdicts"][0].verdict == "stale-version"
    assert result["supported"] == 0


def test_unsupported_claim_flagged():
    result = _evaluator().evaluate(DRAFT_SCENARIOS["draft-unsupported"])
    verdict = result["verdicts"][0]
    assert verdict.verdict == "unsupported"
    assert "cure" in verdict.detail


def test_unknown_source_flagged():
    result = _evaluator().evaluate(DRAFT_SCENARIOS["draft-unknown-source"])
    assert result["verdicts"][0].verdict == "unknown-source"


def test_access_denied_for_restricted_source():
    # BrandB source is reviewer/medical only; a drafter may not cite it.
    claim = DraftClaim("C1", "BrandB infusion is given every 4 weeks",
                       "SRC-PI-303", 1)
    result = _evaluator(role="drafter").evaluate([claim])
    assert result["verdicts"][0].verdict == "access-denied"


def test_reviewer_can_cite_restricted_source():
    claim = DraftClaim("C1", "BrandB infusion is given every 4 weeks",
                       "SRC-PI-303", 1)
    result = _evaluator(role="reviewer").evaluate([claim])
    assert result["verdicts"][0].verdict == "supported"


def test_old_version_still_retrievable_for_replay():
    store = build_store()
    version, text = store.get("SRC-PI-101", version=1, role="drafter")
    assert version == 1
    assert "headache and nausea" in text
    assert store.current_version("SRC-PI-101") == 2


def test_get_missing_version_returns_none():
    store = build_store()
    assert store.get("SRC-PI-101", version=99, role="drafter") is None
    assert store.get("SRC-PI-999", role="drafter") is None


def test_search_returns_source_and_current_version():
    store = build_store()
    results = store.search("BrandA tablets daily food", role="drafter")
    assert results
    assert results[0]["source_id"] == "SRC-PI-101"
    assert results[0]["version"] == 2


def test_search_enforces_role_and_brand():
    store = build_store()
    results = store.search("BrandB infusion clinic", role="drafter")
    assert results == []
    results = store.search("BrandB infusion clinic", role="reviewer",
                           brand="BrandB")
    assert [r["source_id"] for r in results] == ["SRC-PI-303"]


def test_search_scoped_to_brand():
    store = build_store()
    results = store.search("BrandA tablets", role="drafter", brand="BrandB")
    assert results == []


def test_feedback_boosts_source_in_retrieval():
    store = build_store()
    # Both sources match this query; PI-101 wins the tie on source id.
    query = "BrandA tablets patients trial"
    before = [r["source_id"] for r in store.search(query, role="drafter")]
    assert before[0] == "SRC-PI-101"
    feedback = ReviewFeedback("C1", "BrandA tablets once daily with food",
                              "re-cite current version", "SRC-STUDY-202",
                              "BrandA")
    applied = feedback.apply(store)
    after = [r["source_id"] for r in store.search(query, role="drafter")]
    assert applied["boost"] == 1
    assert after[0] == "SRC-STUDY-202"


def test_groundedness_partial():
    claims = DRAFT_SCENARIOS["draft-clean"] + \
        DRAFT_SCENARIOS["draft-unsupported"]
    result = _evaluator().evaluate(claims)
    assert result["total"] == 3
    assert result["supported"] == 2
    assert result["groundedness"] == round(2 / 3, 4)


def test_empty_draft_scores_perfect():
    result = _evaluator().evaluate([])
    assert result["total"] == 0
    assert result["groundedness"] == 1.0
