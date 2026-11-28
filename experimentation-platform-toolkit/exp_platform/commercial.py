"""Commercial measurement: geo-holdout promotional impact and channel attribution.

This is the measurement half of a commercial data-science job (the GCCI
kind): a promotion runs in some territories and not others, and the
question is "how much incremental volume did it cause, and which
channels drove it?" Two tools:

- ``geo_holdout_estimate`` — difference-in-differences on territory
  sales, pre vs post, treated vs holdout territories. It reuses the DiD
  estimator from ``causal.py`` and adds the commercial read-out: the
  per-territory lift and the total incremental volume across treated
  territories.
- ``channel_attribution`` — a linear attribution model: sales regressed
  on promotional touches by channel (rep visits, emails, samples), with
  the intercept as baseline. Each channel's share is its fitted
  contribution as a fraction of total fitted promotional contribution,
  so the shares always sum to 1. Linear attribution is transparent and
  auditable; it is not a claim that channels act independently.

``generate_commercial_panel`` builds seeded synthetic HCP-level data
with a known ground truth (true incremental prescriptions per treated
territory and true per-channel effects), so both estimators can be
checked against a known answer. No real HCPs, patients, claims or
sales data — the shapes (territories, pre/post periods, touch counts)
mirror commercial healthcare data, the numbers are invented.
"""

import numpy as np

from exp_platform.causal import difference_in_differences

CHANNELS = ("rep_visits", "emails", "samples")


def generate_commercial_panel(n_territories=40, hcps_per_territory=15,
                              true_lift=12.0, seed=11):
    """Simulate a geo-holdout promotion test on synthetic HCP data.

    Each territory has a baseline weekly prescription (TRx) level; half
    the territories are treated (promotion on), half are holdout. Treated
    territories gain ``true_lift`` TRx per HCP in the post period. Each
    HCP also gets promotional touches by channel; true per-touch effects
    are rep visits 0.9, emails 0.15, samples 0.5 TRx. Returns a dict of
    arrays plus the ground truth.
    """
    rng = np.random.default_rng(seed)
    n_hcps = n_territories * hcps_per_territory
    territory = np.repeat(np.arange(n_territories), hcps_per_territory)
    treated_terr = np.zeros(n_territories, dtype=int)
    treated_terr[: n_territories // 2] = 1
    rng.shuffle(treated_terr)
    treated = treated_terr[territory]
    # Baseline TRx per HCP: territory level plus HCP variation.
    terr_level = rng.normal(50, 8, size=n_territories)
    hcp_level = terr_level[territory] + rng.normal(0, 5, size=n_hcps)
    pre = np.clip(hcp_level + rng.normal(0, 3, size=n_hcps), 1, None)
    # Promotional touches by channel (post period only, treated HCPs).
    rep_visits = np.where(treated == 1, rng.poisson(4, size=n_hcps),
                          rng.poisson(0.5, size=n_hcps))
    emails = np.where(treated == 1, rng.poisson(6, size=n_hcps),
                      rng.poisson(1, size=n_hcps))
    samples = np.where(treated == 1, rng.poisson(2, size=n_hcps),
                       rng.poisson(0.2, size=n_hcps))
    true_effects = {"rep_visits": 0.9, "emails": 0.15, "samples": 0.5}
    touch_effect = (true_effects["rep_visits"] * rep_visits
                    + true_effects["emails"] * emails
                    + true_effects["samples"] * samples)
    # Post-period sales for the holdout read-out: baseline + treatment
    # lift only, so the DiD ground truth is exactly true_lift.
    post = np.clip(pre + treated * true_lift
                   + rng.normal(0, 3, size=n_hcps), 1, None)
    # Post-period sales for the attribution read-out: baseline + touch
    # effects only (no treatment lift), so the channel ground truth is
    # exactly the per-touch effects above.
    post_attr = np.clip(pre + touch_effect + rng.normal(0, 3, size=n_hcps),
                        1, None)
    return {
        "territory": territory,
        "treated": treated,
        "pre_trx": pre,
        "post_trx": post,
        "post_trx_attribution": post_attr,
        "rep_visits": rep_visits,
        "emails": emails,
        "samples": samples,
        "true_lift": true_lift,
        "true_channel_effects": true_effects,
    }


def geo_holdout_estimate(pre_treat, post_treat, pre_ctrl, post_ctrl):
    """Incremental impact of a geo-holdout promotion (DiD + read-out).

    Inputs are territory-level mean sales, pre and post, for treated and
    holdout territories. Returns the DiD estimate with its 95% CI and
    p-value, plus the total incremental volume across treated
    territories (estimate x number of treated territories).
    """
    out = difference_in_differences(pre_treat, post_treat, pre_ctrl, post_ctrl)
    out["n_treated_territories"] = int(len(np.atleast_1d(pre_treat)))
    out["total_incremental"] = float(
        out["estimate"] * out["n_treated_territories"])
    return out


def channel_attribution(touches, sales, baseline=None):
    """Linear channel attribution: sales ~ touches by channel.

    ``touches`` maps each channel name in CHANNELS to an array of touch
    counts; ``sales`` is the outcome array. Fits OLS with an intercept
    (the intercept is baseline sales with no touches). Pass ``baseline``
    (e.g. pre-period sales per unit) to control for it as a covariate:
    without it, large baseline differences across units swamp the small
    per-touch effects and the channel coefficients are unstable. Returns
    the per-channel coefficient, its fitted contribution (coefficient x
    mean touches), and its share of total fitted promotional
    contribution. Shares are computed from positive contributions only
    and always sum to 1; a channel with a non-positive coefficient gets
    share 0.
    """
    X = np.column_stack([np.asarray(touches[c], dtype=float)
                         for c in CHANNELS])
    y = np.asarray(sales, dtype=float)
    if X.shape[0] != len(y):
        raise ValueError("touches and sales must have the same length")
    if not np.any(X > 0):
        raise ValueError("no promotional touches recorded")
    cols = [np.ones(len(y))]
    if baseline is not None:
        cols.append(np.asarray(baseline, dtype=float))
    cols.append(X)
    X_aug = np.column_stack(cols)
    coef, residuals, rank, _ = np.linalg.lstsq(X_aug, y, rcond=None)
    y_hat = X_aug @ coef
    ss_res = float(((y - y_hat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    offset = 1 + (1 if baseline is not None else 0)
    channel_coef = {c: float(coef[offset + i]) for i, c in enumerate(CHANNELS)}
    contributions = {c: channel_coef[c] * float(X[:, i].mean())
                     for i, c in enumerate(CHANNELS)}
    positive = {c: max(v, 0.0) for c, v in contributions.items()}
    total = sum(positive.values())
    shares = {c: (positive[c] / total if total > 0 else 0.0)
              for c in CHANNELS}
    return {
        "baseline": float(coef[0]),
        "channel_coefficients": channel_coef,
        "channel_contributions": contributions,
        "channel_shares": shares,
        "r_squared": float(r_squared),
    }


def commercial_measurement_report(panel):
    """One-call commercial measurement report for a geo-holdout panel.

    Aggregates the HCP panel to territory means, runs the geo-holdout
    DiD, and runs channel attribution on the HCP-level touches and
    sales. Returns both results in one dict.
    """
    territory = panel["territory"]
    treated = panel["treated"]
    terr_ids = np.unique(territory)
    pre_mean, post_mean, is_treated = [], [], []
    for t in terr_ids:
        mask = territory == t
        pre_mean.append(panel["pre_trx"][mask].mean())
        post_mean.append(panel["post_trx"][mask].mean())
        is_treated.append(bool(treated[mask][0]))
    pre_mean = np.array(pre_mean)
    post_mean = np.array(post_mean)
    is_treated = np.array(is_treated)
    holdout = geo_holdout_estimate(
        pre_mean[is_treated], post_mean[is_treated],
        pre_mean[~is_treated], post_mean[~is_treated])
    attribution = channel_attribution(
        {c: panel[c] for c in CHANNELS},
        panel["post_trx_attribution"],
        baseline=panel["pre_trx"])
    return {
        "geo_holdout": holdout,
        "attribution": attribution,
        "n_territories": int(len(terr_ids)),
        "n_treated_territories": int(is_treated.sum()),
    }
