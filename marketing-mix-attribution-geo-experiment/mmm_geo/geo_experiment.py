"""Geo holdout experiment: difference-in-differences with CUPED adjustment.

Design: paid social is paused in treated DMAs for the post period, control
DMAs keep it. The estimator compares the pre->post change in treated DMAs
against the same change in controls (DiD), and a CUPED variant that
regresses post-period signups on pre-period signups per DMA to cut variance.
A two-sample t-test on DMA-level changes gives the p-value and CI.
"""

import numpy as np
import pandas as pd
from scipy import stats


def analyze_geo(df):
    """Return DiD and CUPED estimates with t-test and 95% CI."""
    piv = (df.groupby(["geo", "period"])["signups"].mean()
             .unstack().reset_index())
    treated = df.drop_duplicates("geo").set_index("geo")["treated"]
    piv["treated"] = piv["geo"].map(treated)
    piv["change"] = piv["post"] - piv["pre"]
    tr = piv[piv["treated"] == 1]["change"].to_numpy()
    ct = piv[piv["treated"] == 0]["change"].to_numpy()

    did = float(np.mean(tr) - np.mean(ct))
    t_stat, p_value = stats.ttest_ind(tr, ct, equal_var=False)
    se = float(np.sqrt(np.var(tr, ddof=1) / len(tr)
                       + np.var(ct, ddof=1) / len(ct)))
    ci = (round(did - 1.96 * se, 1), round(did + 1.96 * se, 1))

    # CUPED: residualise the post-period mean on the pre-period mean.
    slope, intercept, _, _, _ = stats.linregress(piv["pre"], piv["post"])
    piv["post_adj"] = piv["post"] - slope * (piv["pre"] - piv["pre"].mean())
    piv["change_adj"] = piv["post_adj"] - piv["pre"]
    tr_adj = piv[piv["treated"] == 1]["change_adj"].to_numpy()
    ct_adj = piv[piv["treated"] == 0]["change_adj"].to_numpy()
    cuped = float(np.mean(tr_adj) - np.mean(ct_adj))
    _, p_cuped = stats.ttest_ind(tr_adj, ct_adj, equal_var=False)
    se_cuped = float(np.sqrt(np.var(tr_adj, ddof=1) / len(tr_adj)
                             + np.var(ct_adj, ddof=1) / len(ct_adj)))
    ci_cuped = (round(cuped - 1.96 * se_cuped, 1),
                round(cuped + 1.96 * se_cuped, 1))
    return {
        "n_treated_geos": int((piv["treated"] == 1).sum()),
        "n_control_geos": int((piv["treated"] == 0).sum()),
        "did_per_dma_week": round(did, 1),
        "did_p_value": round(float(p_value), 4),
        "did_ci_95": ci,
        "cuped_per_dma_week": round(cuped, 1),
        "cuped_p_value": round(float(p_cuped), 4),
        "cuped_ci_95": ci_cuped,
        # A significantly negative DiD means the pause *cost* signups, so the
        # channel is incremental: keep it running, do not pause it.
        "recommendation": ("KEEP RUNNING" if did < -20 and p_value < 0.05
                           else "INCONCLUSIVE"),
    }
