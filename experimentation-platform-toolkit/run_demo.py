"""Demo: run the full experimentation-platform workflow on synthetic data."""

from exp_platform.data_gen import generate_ab_experiment, generate_did_panel
from exp_platform.report import experiment_report
from exp_platform.causal import difference_in_differences
from exp_platform.commercial import (
    generate_commercial_panel,
    commercial_measurement_report,
)


def main():
    data = generate_ab_experiment()
    rep = experiment_report(data)
    print(f"Control rate:   {rep['rate_control']:.4f} (n={rep['n_control']})")
    print(f"Treatment rate: {rep['rate_treatment']:.4f} (n={rep['n_treatment']})")
    print(f"Observed lift:  {rep['lift']:.4f} (true lift {rep['true_lift']:.4f})")
    print(f"Naive z: {rep['naive_z']:.2f}, p = {rep['naive_p_value']:.4f}")
    print(f"SRM detected:  {rep['srm']['srm_detected']} "
          f"(p = {rep['srm']['p_value']:.3f})")
    print(f"CUPED: theta = {rep['cuped_theta']:.3f}, "
          f"variance reduction = {rep['cuped_variance_reduction']:.1%}, "
          f"adjusted lift = {rep['cuped_lift']:.4f} (z = {rep['cuped_z']:.2f})")
    print(f"Bayesian: P(B > A) = {rep['bayesian']['prob_b_beats_a']:.3f}, "
          f"expected loss of shipping B = "
          f"{rep['bayesian']['expected_loss_ship_b']:.5f}")
    print(f"Sequential (look 5/5): boundary = "
          f"{rep['sequential']['boundary']:.2f}, "
          f"crossed = {rep['sequential']['crossed']}")
    print(f"Sample size needed per variant: {rep['sample_size_per_variant']}")
    print(f"MDE at current n: {rep['mde_at_current_n']:.4f}")

    panel = generate_did_panel()
    did = difference_in_differences(
        panel["pre"][panel["treated"] == 1].mean(axis=1),
        panel["post"][panel["treated"] == 1].mean(axis=1),
        panel["pre"][panel["treated"] == 0].mean(axis=1),
        panel["post"][panel["treated"] == 0].mean(axis=1),
    )
    print(f"DiD estimate: {did['estimate']:.2f} "
          f"(true {panel['true_effect']:.1f}), p = {did['p_value']:.4f}")

    comm = generate_commercial_panel()
    crep = commercial_measurement_report(comm)
    hold = crep["geo_holdout"]
    print(f"Geo-holdout: +{hold['estimate']:.2f} TRx per treated territory "
          f"(true {comm['true_lift']:.1f}), p = {hold['p_value']:.4f}, "
          f"total incremental {hold['total_incremental']:.0f} TRx across "
          f"{hold['n_treated_territories']} treated territories")
    attr = crep["attribution"]
    print("Attribution shares (R2 = "
          f"{attr['r_squared']:.2f}): " +
          ", ".join(f"{c} {attr['channel_shares'][c]:.1%}"
                    for c in ("rep_visits", "emails", "samples")))


if __name__ == "__main__":
    main()
