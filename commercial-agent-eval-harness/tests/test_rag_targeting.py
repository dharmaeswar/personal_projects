"""Tests for the Cash Equities client-targeting + RAG evaluation."""

import math

from agent_eval.rag_targeting import (
    GROUNDED_CLAIMS, LOOSE_CLAIMS, SOURCES, WEIGHTS,
    build_client_flow, compare_prompt_variants, evaluate_draft,
    rank_clients, render_cash_equities_report, run_cash_equities_eval,
    score_client,
)


def test_dataset_is_deterministic_and_complete():
    first = build_client_flow()
    second = build_client_flow()
    assert first == second
    assert len(first) == 12
    for client in first:
        for field in ("client_id", "name", "sector", "flow_usd_m", "axes",
                      "iois", "idea_match", "event", "last_contact_days"):
            assert field in client


def test_weights_sum_to_one():
    assert math.isclose(sum(WEIGHTS.values()), 1.0)


def test_score_bounds():
    clients = build_client_flow()
    max_flow = max(c["flow_usd_m"] for c in clients)
    for client in clients:
        score, _ = score_client(client, max_flow)
        assert 0.0 <= score <= 100.0


def test_higher_flow_scores_higher_all_else_equal():
    base = {"client_id": "X", "name": "X", "sector": "Tech",
            "flow_usd_m": 10.0, "axes": 2, "iois": 1, "idea_match": 0.5,
            "event": False, "last_contact_days": 5}
    high = dict(base, flow_usd_m=40.0)
    low_score, _ = score_client(base, 40.0)
    high_score, _ = score_client(high, 40.0)
    assert high_score > low_score


def test_event_adds_fifteen_points():
    base = {"client_id": "X", "name": "X", "sector": "Tech",
            "flow_usd_m": 10.0, "axes": 2, "iois": 1, "idea_match": 0.5,
            "event": False, "last_contact_days": 5}
    no_event, _ = score_client(base, 40.0)
    with_event, _ = score_client(dict(base, event=True), 40.0)
    assert math.isclose(with_event - no_event, 15.0)


def test_liquidity_saturates_at_cap():
    base = {"client_id": "X", "name": "X", "sector": "Tech",
            "flow_usd_m": 10.0, "axes": 6, "iois": 6, "idea_match": 0.5,
            "event": False, "last_contact_days": 5}
    capped = dict(base, axes=20, iois=20)
    score, _ = score_client(base, 40.0)
    capped_score, _ = score_client(capped, 40.0)
    assert math.isclose(score, capped_score)


def test_score_rejects_nonpositive_max_flow():
    client = build_client_flow()[0]
    try:
        score_client(client, 0)
    except ValueError:
        return
    raise AssertionError("expected ValueError for max_flow=0")


def test_ranking_is_sorted_with_ranks_and_rationale():
    ranked = rank_clients(build_client_flow())
    assert len(ranked) == 12
    scores = [r["score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)
    assert [r["rank"] for r in ranked] == list(range(1, 13))
    for entry in ranked:
        assert entry["rationale"]
        assert any("flow" in r for r in entry["rationale"])


def test_ranking_empty_input():
    assert rank_clients([]) == []


def test_rag_supported_claim():
    result = evaluate_draft(GROUNDED_CLAIMS, SOURCES)
    assert result["groundedness"] == 1.0
    assert result["supported"] == 3
    assert result["hallucinated"] is False
    assert all(v["verdict"] == "supported" for v in result["claims"])


def test_rag_flags_unsupported_claim():
    result = evaluate_draft(LOOSE_CLAIMS, SOURCES)
    assert result["supported"] == 3
    assert result["total"] == 4
    assert result["groundedness"] == 0.75
    assert result["hallucinated"] is True
    assert result["claims"][-1]["verdict"] == "unsupported"


def test_rag_missing_source():
    claims = [{"text": "x", "source_id": "nope", "keywords": ["x"]}]
    result = evaluate_draft(claims, SOURCES)
    assert result["claims"][0]["verdict"] == "missing_source"
    assert result["groundedness"] == 0.0
    assert result["hallucinated"] is True


def test_rag_empty_claims_is_fully_grounded():
    result = evaluate_draft([], SOURCES)
    assert result["groundedness"] == 1.0
    assert result["hallucinated"] is False


def test_prompt_comparison_picks_grounded_variant():
    comparison = compare_prompt_variants([
        {"name": "grounded-prompt", "claims": GROUNDED_CLAIMS,
         "sources": SOURCES},
        {"name": "loose-prompt", "claims": LOOSE_CLAIMS,
         "sources": SOURCES},
    ])
    assert comparison["best"] == "grounded-prompt"
    assert comparison["variants"][0]["groundedness"] == 1.0
    assert comparison["variants"][1]["groundedness"] == 0.75


def test_full_eval_passes():
    result = run_cash_equities_eval()
    assert result["verdict"] == "PASS"
    assert result["ranked_count"] == 12
    assert len(result["top_clients"]) == 5
    assert result["top_clients"][0]["score"] >= 50


def test_report_renders():
    text = render_cash_equities_report(run_cash_equities_eval())
    assert "PASS" in text
    assert "Top 5 clients to call" in text
    assert "grounded-prompt" in text
