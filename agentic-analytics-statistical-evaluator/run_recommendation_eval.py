"""Run the next-best-action recommendation evaluation and write the report.

Usage: python run_recommendation_eval.py
Writes recommendation_eval_report.txt in this directory.
"""

from agentic_stats.recommendation import compare_rankers


def main():
    result = compare_rankers()
    base = result["baseline"]
    pers = result["personalized"]
    lo, hi = result["ci_95"]
    lines = [
        "Next-best-action recommendation evaluation (seeded synthetic data)",
        f"Users: {result['n_users']}, k={result['k']}",
        "",
        "Popularity baseline:",
        f"  mean precision@{result['k']}: {base['mean_precision']:.3f}",
        f"  mean recall@{result['k']}:    {base['mean_recall']:.3f}",
        f"  mean NDCG@{result['k']}:      {base['mean_ndcg']:.3f}",
        f"  catalog coverage:  {base['coverage']:.3f}",
        "",
        "Personalised ranker:",
        f"  mean precision@{result['k']}: {pers['mean_precision']:.3f}",
        f"  mean recall@{result['k']}:    {pers['mean_recall']:.3f}",
        f"  mean NDCG@{result['k']}:      {pers['mean_ndcg']:.3f}",
        f"  catalog coverage:  {pers['coverage']:.3f}",
        "",
        "Statistical gate (per-user NDCG, personalised vs baseline):",
        f"  NDCG difference: {result['ndcg_diff']:+.3f}",
        f"  Welch t = {result['welch_t']:.2f}, p = {result['welch_p']:.2g}",
        f"  Bootstrap 95% CI on the difference: ({lo:+.3f}, {hi:+.3f})",
        f"  Significant improvement: {result['significant']}",
        f"  Coverage guardrail (>= 0.25 of catalog): {result['guardrail_ok']}",
        "",
        f"Verdict: {result['verdict']}",
    ]
    text = "\n".join(lines) + "\n"
    print(text, end="")
    with open("recommendation_eval_report.txt", "w") as f:
        f.write(text)


if __name__ == "__main__":
    main()
