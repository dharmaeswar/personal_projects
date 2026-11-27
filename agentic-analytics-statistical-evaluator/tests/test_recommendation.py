"""Tests for the next-best-action recommendation evaluation."""

import math

from agentic_stats.recommendation import (
    compare_rankers,
    coverage,
    generate_catalog,
    generate_history,
    generate_users,
    held_out_relevant,
    ndcg_at_k,
    personalized_ranker,
    popularity_ranker,
    precision_at_k,
    recall_at_k,
)


def test_precision_at_k_hand_computed():
    assert precision_at_k(["a", "b", "c"], {"a", "c"}, k=3) == 2 / 3


def test_recall_at_k_hand_computed():
    assert recall_at_k(["a", "b", "c"], {"a", "c", "d", "e"}, k=3) == 2 / 4


def test_ndcg_at_k_hand_computed():
    ranked = ["a", "x", "b"]
    relevant = {"a", "b"}
    dcg = 1.0 / math.log2(2) + 1.0 / math.log2(4)
    ideal = 1.0 / math.log2(2) + 1.0 / math.log2(3)
    assert abs(ndcg_at_k(ranked, relevant, k=3) - dcg / ideal) < 1e-9


def test_ndcg_perfect_ranking_is_one():
    assert ndcg_at_k(["a", "b"], {"a", "b"}, k=2) == 1.0


def test_ndcg_no_hits_is_zero():
    assert ndcg_at_k(["x", "y"], {"a", "b"}, k=2) == 0.0


def test_generation_is_deterministic():
    users_a = generate_users()
    users_b = generate_users()
    assert users_a == users_b
    catalog_a = generate_catalog()
    history_a = generate_history(users_a, catalog_a)
    history_b = generate_history(users_b, catalog_a)
    assert history_a == history_b


def test_personalized_never_recommends_seen_items():
    users = generate_users()
    catalog = generate_catalog()
    history = generate_history(users, catalog)
    for user in users[:20]:
        ranked = personalized_ranker(user, history[user["user_id"]], catalog)
        assert not set(ranked) & set(history[user["user_id"]])


def test_cold_start_falls_back_to_popularity():
    users = generate_users()
    catalog = generate_catalog()
    history = generate_history(users, catalog)
    popular = popularity_ranker(history, catalog, k=5)
    ranked = personalized_ranker(users[0], [], catalog, k=5, fallback=popular)
    assert ranked == popular


def test_popularity_ranker_orders_by_global_counts():
    catalog = [
        {"item_id": "a", "topic": "taxes", "quality": 0.9},
        {"item_id": "b", "topic": "taxes", "quality": 0.9},
        {"item_id": "c", "topic": "taxes", "quality": 0.9},
    ]
    history = {"u1": ["a", "b"], "u2": ["a"], "u3": ["b", "c"]}
    assert popularity_ranker(history, catalog, k=3) == ["a", "b", "c"]


def test_coverage_counts_surfaced_items():
    catalog = [{"item_id": f"i{n}"} for n in range(10)]
    assert coverage([["i0", "i1"], ["i1", "i2"]], catalog) == 0.3


def test_personalized_beats_popularity_and_ships():
    result = compare_rankers()
    assert result["verdict"] == "SHIP"
    assert result["personalized"]["mean_ndcg"] > result["baseline"]["mean_ndcg"]
    assert result["ndcg_diff"] > 0.2
    assert result["welch_p"] < 0.05
    assert result["ci_95"][0] > 0
    assert result["significant"] is True
    assert result["guardrail_ok"] is True


def test_personalized_covers_more_of_the_catalog():
    result = compare_rankers()
    assert result["personalized"]["coverage"] >= 0.25
    assert result["personalized"]["coverage"] > result["baseline"]["coverage"]


def test_held_out_relevant_never_overlaps_history():
    users = generate_users()
    catalog = generate_catalog()
    history = generate_history(users, catalog)
    relevant = held_out_relevant(users, catalog, history)
    for user in users:
        assert not relevant[user["user_id"]] & set(history[user["user_id"]])
        assert len(relevant[user["user_id"]]) == 5
