"""End-to-end run: KPIs, health mix, propensity models, experiments, next best action.

Usage: python run_analysis.py
Prints every result the README quotes, so the numbers in the README are the
numbers this script actually produced on the seeded synthetic data.
"""
from customer_success import data, health, propensity, experiments, kpis
from customer_success.next_best_action import next_best_actions


def main():
    customers = data.generate()
    scored = health.score_all(customers)
    print("== KPIs ==")
    for key, val in kpis.compute_kpis(customers).items():
        print(f"  {key}: {val}")
    print("== Health mix ==", health.health_mix(scored))
    print("== Retention by health band ==", health.retention_by_band(scored))

    rows, churn_labels = data.features_matrix(customers, "retained")
    _, expand_labels = data.features_matrix(customers, "expanded")
    churn_labels = [1 - y for y in churn_labels]  # model churn (1 = churned)
    tr_rows, tr_y, te_rows, te_y = propensity.train_test_split(rows, churn_labels)
    churn_model = propensity.train_logistic(tr_rows, tr_y)
    print("== Churn model (held-out) ==", propensity.evaluate(churn_model, te_rows, te_y))
    tr_rows, tr_y, te_rows, te_y = propensity.train_test_split(rows, expand_labels)
    expand_model = propensity.train_logistic(tr_rows, tr_y)
    print("== Expansion model (held-out) ==", propensity.evaluate(expand_model, te_rows, te_y))

    print("== Onboarding A/B (randomized) ==")
    treat = [c for c in customers if c["onboard_treat"]]
    control = [c for c in customers if not c["onboard_treat"]]
    print("  SRM:", experiments.srm_chi2(len(treat), len(control)))
    print("  time-to-value:", experiments.welch_ttest(
        [c["time_to_value_days"] for c in treat],
        [c["time_to_value_days"] for c in control]))
    print("  retention:", experiments.welch_ttest(
        [1 if c["retained"] else 0 for c in treat],
        [1 if c["retained"] else 0 for c in control]))
    adj_t, theta = experiments.cuped_adjust(
        [c["usage_post"] for c in treat], [c["usage_pre"] for c in treat],
        theta=experiments.cuped_theta(
            [c["usage_post"] for c in customers], [c["usage_pre"] for c in customers]))
    adj_c, _ = experiments.cuped_adjust(
        [c["usage_post"] for c in control], [c["usage_pre"] for c in control],
        theta=experiments.cuped_theta(
            [c["usage_post"] for c in customers], [c["usage_pre"] for c in customers]))
    print("  CUPED theta (treat arm):", theta)
    print("  CUPED usage_post:", experiments.welch_ttest(adj_t, adj_c))

    print("== Coverage investment (non-randomized rollout) ==")
    cov = [c for c in customers if c["coverage_treat"]]
    nocov = [c for c in customers if not c["coverage_treat"]]
    did = experiments.difference_in_differences(
        [c["usage_pre"] for c in cov], [c["usage_post"] for c in cov],
        [c["usage_pre"] for c in nocov], [c["usage_post"] for c in nocov])
    print("  DiD on usage (planted +0.08):", did)
    series = data.weekly_series(customers)
    sc = experiments.synthetic_control(
        series["treated_pre"], series["donors_pre"],
        series["treated_post"], series["donors_post"])
    print("  Synthetic control (donors:", series["donor_names"], "):", sc)

    print("== Next best action (sample) ==")
    churn_p = propensity.predict_proba(churn_model, rows)
    expand_p = propensity.predict_proba(expand_model, rows)
    for c, cp, ep in list(zip(scored, churn_p, expand_p))[:3]:
        print(f"  customer {c['customer_id']} [{c['health_band']}, "
              f"churn_p={cp:.2f}, expand_p={ep:.2f}]:",
              next_best_actions(c, cp, ep)[0])


if __name__ == "__main__":
    main()
