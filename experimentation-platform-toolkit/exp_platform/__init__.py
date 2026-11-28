"""Experimentation platform toolkit.

End-to-end statistical tooling for running trustworthy A/B tests at scale:
experiment design (power / sample size), CUPED variance reduction, group
sequential monitoring, causal-inference estimators (difference-in-differences,
uplift) and Bayesian decision rules — all on seeded synthetic data.

Nothing here touches real users or real experiment data. Ground-truth
parameters are written into the generator so every estimate can be checked
against a known answer.
"""

from exp_platform.design import (
    sample_size_proportion,
    sample_size_continuous,
    minimum_detectable_effect,
    check_srm,
)
from exp_platform.cuped import cuped_adjust, cuped_theta
from exp_platform.sequential import obf_boundaries, sequential_decision
from exp_platform.causal import (
    difference_in_differences,
    bayesian_ab_test,
    uplift_t_learner,
)
from exp_platform.report import experiment_report
from exp_platform.commercial import (
    CHANNELS,
    channel_attribution,
    commercial_measurement_report,
    generate_commercial_panel,
    geo_holdout_estimate,
)

__all__ = [
    "sample_size_proportion",
    "sample_size_continuous",
    "minimum_detectable_effect",
    "check_srm",
    "cuped_adjust",
    "cuped_theta",
    "obf_boundaries",
    "sequential_decision",
    "difference_in_differences",
    "bayesian_ab_test",
    "uplift_t_learner",
    "experiment_report",
    "CHANNELS",
    "channel_attribution",
    "commercial_measurement_report",
    "generate_commercial_panel",
    "geo_holdout_estimate",
]
