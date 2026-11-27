"""Next-best-action recommendation evaluation for Consumer Group AI.

The second front of the Consumer Group AI role is in-product recommendation
and personalization: surfacing the right guidance, products and
next-best-actions. This module evaluates a personalised next-best-action
ranker against a popularity baseline on seeded synthetic data, using the
same statistical gate as the rest of this project (Welch t-test plus
bootstrap confidence interval), so a win is only called a win when it is
real, not noise.

All data is synthetic and seeded. No real user, product or Intuit data is
used. The "model" is a plain-Python content-based scorer (a user's topic
profile from their own history, times item quality); no ML library is
called and nothing here claims a production recommender was built.
Standard library only.
"""

import math
import random

from .stats import bootstrap_ci_mean_diff, mean, welch_t_test

TOPICS = ("budgeting", "taxes", "invoicing", "payroll", "saving")
N_ITEMS = 40
N_USERS = 200
K = 5


def generate_catalog(n_items=N_ITEMS, seed=42):
    """Guidance cards: each has a topic and a quality score in [0.6, 1.0]."""
    rng = random.Random(seed)
    catalog = []
    for i in range(n_items):
        catalog.append({
            "item_id": f"card-{i:02d}",
            "topic": TOPICS[i % len(TOPICS)],
            "quality": round(rng.uniform(0.6, 1.0), 3),
        })
    return catalog


def generate_users(n_users=N_USERS, seed=42):
    """Users with a true topic-affinity profile (sums to 1, one dominant topic)."""
    rng = random.Random(seed + 1)
    users = []
    for u in range(n_users):
        weights = [rng.random() ** 2 for _ in TOPICS]
        dominant = rng.randrange(len(TOPICS))
        weights[dominant] += 2.0
        total = sum(weights)
        users.append({
            "user_id": f"user-{u:03d}",
            "affinity": {t: round(w / total, 3) for t, w in zip(TOPICS, weights)},
        })
    return users


def generate_history(users, catalog, n_train=6, seed=42):
    """Observed interactions: items sampled in proportion to affinity x quality."""
    rng = random.Random(seed + 2)
    by_topic = {t: [c for c in catalog if c["topic"] == t] for t in TOPICS}
    history = {}
    for user in users:
        seen = []
        weights = []
        for card in catalog:
            weights.append(user["affinity"][card["topic"]] * card["quality"])
        pool = list(range(len(catalog)))
        for _ in range(n_train):
            pick = rng.choices(pool, weights=[weights[i] for i in pool], k=1)[0]
            pool.remove(pick)
            seen.append(catalog[pick]["item_id"])
        history[user["user_id"]] = seen
    return history


def held_out_relevant(users, catalog, history, n_relevant=5, seed=42):
    """Ground-truth relevant items: unseen cards from the user's top-2 topics."""
    rng = random.Random(seed + 3)
    relevant = {}
    for user in users:
        top_topics = sorted(user["affinity"], key=user["affinity"].get, reverse=True)[:2]
        seen = set(history[user["user_id"]])
        candidates = [c for c in catalog if c["topic"] in top_topics and c["item_id"] not in seen]
        rng.shuffle(candidates)
        relevant[user["user_id"]] = {c["item_id"] for c in candidates[:n_relevant]}
    return relevant


def popularity_ranker(history, catalog, k=K):
    """Baseline: rank by how many users interacted with the card (global counts)."""
    counts = {c["item_id"]: 0 for c in catalog}
    for seen in history.values():
        for item_id in seen:
            counts[item_id] += 1
    ranked = sorted(
        catalog,
        key=lambda c: (-counts[c["item_id"]], -c["quality"], c["item_id"]),
    )
    return [c["item_id"] for c in ranked[:k]]


def personalized_ranker(user, history_user, catalog, k=K, fallback=None):
    """Content-based ranker: user topic profile from history, times quality.

    A user with no history (cold start) falls back to the popularity order
    passed in as ``fallback``; with no fallback either, quality order is used.
    """
    by_id = {c["item_id"]: c for c in catalog}
    if not history_user:
        if fallback is not None:
            return list(fallback[:k])
        return [c["item_id"] for c in sorted(catalog, key=lambda c: (-c["quality"], c["item_id"]))[:k]]
    profile = {t: 0.0 for t in TOPICS}
    for item_id in history_user:
        profile[by_id[item_id]["topic"]] += 1.0
    total = sum(profile.values())
    profile = {t: v / total for t, v in profile.items()}
    seen = set(history_user)
    scored = sorted(
        (c for c in catalog if c["item_id"] not in seen),
        key=lambda c: (-profile[c["topic"]] * c["quality"], c["item_id"]),
    )
    return [c["item_id"] for c in scored[:k]]


def precision_at_k(ranked, relevant, k=K):
    ranked = ranked[:k]
    if not ranked:
        return 0.0
    return sum(1 for item_id in ranked if item_id in relevant) / len(ranked)


def recall_at_k(ranked, relevant, k=K):
    if not relevant:
        return 0.0
    return sum(1 for item_id in ranked[:k] if item_id in relevant) / len(relevant)


def ndcg_at_k(ranked, relevant, k=K):
    ranked = ranked[:k]
    dcg = sum(1.0 / math.log2(i + 2) for i, item_id in enumerate(ranked) if item_id in relevant)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal else 0.0


def evaluate_ranker(rank_fn, users, catalog, history, relevant, k=K):
    """Per-user precision, recall and NDCG for one ranker.

    ``rank_fn`` takes (user, history_for_user, catalog) and returns a ranked
    list of item ids.
    """
    per_user = []
    for user in users:
        ranked = rank_fn(user, history[user["user_id"]], catalog)
        rel = relevant[user["user_id"]]
        per_user.append({
            "user_id": user["user_id"],
            "precision": precision_at_k(ranked, rel, k),
            "recall": recall_at_k(ranked, rel, k),
            "ndcg": ndcg_at_k(ranked, rel, k),
            "ranked": ranked,
        })
    return per_user


def coverage(ranked_lists, catalog):
    """Fraction of the catalog that appears in at least one top-k list."""
    surfaced = {item_id for ranked in ranked_lists for item_id in ranked}
    return len(surfaced) / len(catalog)


def compare_rankers(users=None, catalog=None, history=None, relevant=None, k=K):
    """Personalised vs popularity on NDCG@k, with the statistical gate.

    Returns the per-user metric tables for both rankers plus a verdict:
    SHIP only when personalised NDCG is significantly higher (Welch p < 0.05
    and the bootstrap 95% CI excludes zero) and the personalised ranker
    surfaces at least 25% of the catalog (coverage guardrail — a ranker
    that only ever shows a handful of cards is not personalisation).
    """
    users = users if users is not None else generate_users()
    catalog = catalog if catalog is not None else generate_catalog()
    history = history if history is not None else generate_history(users, catalog)
    relevant = relevant if relevant is not None else held_out_relevant(users, catalog, history)
    popular = popularity_ranker(history, catalog, k)
    base_results = evaluate_ranker(
        lambda u, h, c: popular, users, catalog, history, relevant, k)
    pers_results = evaluate_ranker(
        lambda u, h, c: personalized_ranker(u, h, c, k, fallback=popular),
        users, catalog, history, relevant, k)
    base_ndcg = [r["ndcg"] for r in base_results]
    pers_ndcg = [r["ndcg"] for r in pers_results]
    test = welch_t_test(pers_ndcg, base_ndcg)
    ci_low, ci_high = bootstrap_ci_mean_diff(pers_ndcg, base_ndcg)
    pers_cov = coverage([r["ranked"] for r in pers_results], catalog)
    base_cov = coverage([r["ranked"] for r in base_results], catalog)
    significant = test["p"] < 0.05 and ci_low > 0
    guardrail_ok = pers_cov >= 0.25
    verdict = "SHIP" if (significant and guardrail_ok) else "DO NOT SHIP"
    return {
        "k": k,
        "n_users": len(users),
        "baseline": {
            "mean_precision": mean([r["precision"] for r in base_results]),
            "mean_recall": mean([r["recall"] for r in base_results]),
            "mean_ndcg": mean(base_ndcg),
            "coverage": base_cov,
        },
        "personalized": {
            "mean_precision": mean([r["precision"] for r in pers_results]),
            "mean_recall": mean([r["recall"] for r in pers_results]),
            "mean_ndcg": mean(pers_ndcg),
            "coverage": pers_cov,
        },
        "ndcg_diff": mean(pers_ndcg) - mean(base_ndcg),
        "welch_t": test["t"],
        "welch_p": test["p"],
        "ci_95": (ci_low, ci_high),
        "significant": significant,
        "guardrail_ok": guardrail_ok,
        "verdict": verdict,
        "baseline_per_user": base_results,
        "personalized_per_user": pers_results,
    }
