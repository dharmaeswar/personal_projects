"""Synthetic two-arm experiment dataset.

A deterministic, invented dataset for demonstrating the pipeline — no real
subjects, no real trial data. Ground truth (built into the generator):

* Primary outcome: treatment beats control by about 0.8 standard deviations.
* Secondary outcome: no treatment effect at all.
* Subgroup (flagged "high-baseline" participants): the apparent benefit is
  noise from a small, cherry-picked slice — it must not survive validation.
* Responder rate (categorical): treatment responders are genuinely more
  frequent than control responders.
"""

import random


def build_dataset(n_per_arm=120, seed=7):
    rng = random.Random(seed)
    rows = []
    for arm in ("control", "treatment"):
        for i in range(n_per_arm):
            baseline = rng.gauss(50.0, 10.0)
            # Primary outcome: real treatment effect of +8 points.
            primary = baseline + rng.gauss(0.0, 5.0)
            if arm == "treatment":
                primary += 8.0
            # Secondary outcome: no effect in either arm.
            secondary = rng.gauss(100.0, 15.0)
            # Responder: treatment genuinely responds more often.
            p_resp = 0.50 if arm == "treatment" else 0.28
            responder = rng.random() < p_resp
            # Subgroup flag: top third of baseline values.
            subgroup = "high-baseline" if baseline > 55.0 else "low-baseline"
            rows.append({
                "id": f"{arm}-{i:03d}",
                "arm": arm,
                "baseline": round(baseline, 2),
                "primary": round(primary, 2),
                "secondary": round(secondary, 2),
                "responder": responder,
                "subgroup": subgroup,
            })
    return rows


def split_arms(rows):
    control = [r for r in rows if r["arm"] == "control"]
    treatment = [r for r in rows if r["arm"] == "treatment"]
    return control, treatment
