"""Card-fraud rule backtesting, shadow testing, staged rollouts, and KRIs.

New module, Nov 2026 (Mercury Senior Risk Strategist packaging): the
fraud-scoring model validation already in this project answers "is the
model good?". This module answers the strategist's question: "are the
rules we run on live traffic good?" — author a rule, backtest it on
seeded synthetic card transactions, compare a challenger rule set in
shadow mode (decisions recorded, not enforced), simulate a staged
rollout, tune a model-score threshold by weighing false positives
against fraud loss, and track key risk indicators (KRIs) for an
executive-ready view.

All data is synthetic and seeded (see ``fraud_validation.data``). No
real bank, cardholder, or transaction data is used, and nothing here
is a claim about any real institution or any real card-fraud program.
A rule backtested here is a demonstration of the method, not a rule
that was ever run against live traffic.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Review cost per false positive sent to manual review, in dollars.
REVIEW_COST_USD = 25.0


def rule_flags(df: pd.DataFrame, rule: str) -> pd.Series:
    """Return the boolean flag mask for one named card-fraud rule.

    Rules mirror common card-fraud typologies on the synthetic fields:

    - ``velocity_1h_burst``: 5+ transactions in the last hour — the
      card-testing pattern (rapid low-value attempts on one card).
    - ``cross_border_cnp_high_amount``: cross-border, card-not-present,
      amount >= $200.
    - ``new_device_night``: device younger than 30 days and a night
      hour (23:00-04:59).
    - ``high_amount``: single transaction amount >= $1,000.
    - ``velocity_24h_surge``: 25+ transactions in the last 24 hours.
    """
    if rule == "velocity_1h_burst":
        return df["velocity_1h"] >= 5
    if rule == "cross_border_cnp_high_amount":
        return (df["cross_border"] == 1) & (df["card_present"] == 0) & (df["amount"] >= 200)
    if rule == "new_device_night":
        night = (df["hour"] < 5) | (df["hour"] >= 23)
        return (df["device_age_days"] < 30) & night
    if rule == "high_amount":
        return df["amount"] >= 1000
    if rule == "velocity_24h_surge":
        return df["velocity_24h"] >= 25
    raise ValueError(f"Unknown rule: {rule}")


RULES = [
    "velocity_1h_burst",
    "cross_border_cnp_high_amount",
    "new_device_night",
    "high_amount",
    "velocity_24h_surge",
]

RULE_DESCRIPTIONS = {
    "velocity_1h_burst": "5+ transactions in 1h (card-testing pattern)",
    "cross_border_cnp_high_amount": "cross-border CNP amount >= $200",
    "new_device_night": "device < 30 days old, night hour",
    "high_amount": "amount >= $1,000",
    "velocity_24h_surge": "25+ transactions in 24h",
}


def combine_flags(df: pd.DataFrame, rules: list[str]) -> pd.Series:
    """OR-combine the flags of several rules into one decision mask."""
    combined = pd.Series(False, index=df.index)
    for rule in rules:
        combined = combined | rule_flags(df, rule)
    return combined


def evaluate_rule(
    df: pd.DataFrame, flags: pd.Series
) -> dict:
    """Score one rule (or rule set) against the fraud labels.

    Returns flagged counts, fraud caught, precision/recall, false
    positives, fraud loss avoided (fraud dollars flagged), and the
    false-positive review burden in dollars at REVIEW_COST_USD each.
    """
    y = df["is_fraud"].to_numpy().astype(bool)
    f = flags.to_numpy().astype(bool)
    amount = df["amount"].to_numpy(dtype=float)
    n_flagged = int(f.sum())
    fraud_caught = int((f & y).sum())
    false_positives = int((f & ~y).sum())
    total_fraud = int(y.sum())
    total_fraud_loss = float(amount[y].sum())
    fraud_loss_avoided = float(amount[f & y].sum())
    return {
        "n_flagged": n_flagged,
        "flag_rate": float(n_flagged / len(df)) if len(df) else 0.0,
        "fraud_caught": fraud_caught,
        "fraud_capture": float(fraud_caught / total_fraud) if total_fraud else 0.0,
        "precision": float(fraud_caught / n_flagged) if n_flagged else 0.0,
        "false_positives": false_positives,
        "fraud_loss_avoided": fraud_loss_avoided,
        "fraud_loss_share": float(fraud_loss_avoided / total_fraud_loss) if total_fraud_loss else 0.0,
        "review_cost": float(false_positives * REVIEW_COST_USD),
    }


def backtest_rules(df: pd.DataFrame, rules: list[str] | None = None) -> pd.DataFrame:
    """Backtest every rule on ``df``; one row per rule plus a combined row."""
    rules = list(rules) if rules is not None else list(RULES)
    rows = []
    for rule in rules:
        row = evaluate_rule(df, rule_flags(df, rule))
        row["rule"] = rule
        row["description"] = RULE_DESCRIPTIONS[rule]
        rows.append(row)
    combined = evaluate_rule(df, combine_flags(df, rules))
    combined["rule"] = "ALL_RULES_COMBINED"
    combined["description"] = "OR of all rules above"
    rows.append(combined)
    cols = ["rule", "description", "n_flagged", "flag_rate", "fraud_caught",
            "fraud_capture", "precision", "false_positives",
            "fraud_loss_avoided", "fraud_loss_share", "review_cost"]
    return pd.DataFrame(rows, columns=cols)


def shadow_test(
    df: pd.DataFrame,
    champion_rules: list[str],
    challenger_rules: list[str],
) -> dict:
    """Compare a challenger rule set against the champion in shadow mode.

    Both sets are scored on the same transactions; the challenger
    decision is recorded only, never enforced. Returns each set's
    evaluation plus the deltas (challenger minus champion).
    """
    champion = evaluate_rule(df, combine_flags(df, champion_rules))
    challenger = evaluate_rule(df, combine_flags(df, challenger_rules))
    deltas = {
        key: challenger[key] - champion[key]
        for key in ("n_flagged", "fraud_caught", "false_positives",
                    "fraud_loss_avoided", "review_cost")
    }
    deltas["fraud_capture"] = challenger["fraud_capture"] - champion["fraud_capture"]
    deltas["precision"] = challenger["precision"] - champion["precision"]
    return {
        "champion_rules": list(champion_rules),
        "challenger_rules": list(challenger_rules),
        "champion": champion,
        "challenger": challenger,
        "deltas": deltas,
    }


def staged_rollout(
    df: pd.DataFrame,
    flags: pd.Series,
    stages: tuple[float, ...] = (0.10, 0.25, 0.50, 1.00),
    seed: int = 42,
) -> pd.DataFrame:
    """Simulate a staged rollout: expose the rule to a growing seeded slice.

    Each stage takes the first ``fraction`` of a seeded shuffle, so a
    stage's slice always contains the previous stage's slice. Reports
    the same outcome metrics at each exposure level.
    """
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(df))
    rows = []
    for fraction in stages:
        n = max(1, int(round(len(df) * fraction)))
        idx = order[:n]
        sub = df.iloc[idx]
        row = evaluate_rule(sub, flags.iloc[idx].reset_index(drop=True))
        row["stage_fraction"] = fraction
        row["n_transactions"] = n
        rows.append(row)
    cols = ["stage_fraction", "n_transactions", "n_flagged", "flag_rate",
            "fraud_caught", "fraud_capture", "precision", "false_positives",
            "fraud_loss_avoided", "fraud_loss_share", "review_cost"]
    return pd.DataFrame(rows, columns=cols)


def tune_score_threshold(
    y_true: np.ndarray,
    scores: np.ndarray,
    amounts: np.ndarray,
    review_cost: float = REVIEW_COST_USD,
    thresholds: np.ndarray | None = None,
) -> dict:
    """Pick the model-score threshold that minimises total decision cost.

    Total cost = false positives x review cost + missed fraud dollars.
    This is the explicit false-positive vs fraud-loss trade-off a
    strategist weighs when setting a threshold on model scores.
    """
    y = np.asarray(y_true).astype(bool)
    s = np.asarray(scores, dtype=float)
    amt = np.asarray(amounts, dtype=float)
    if thresholds is None:
        thresholds = np.round(np.arange(0.05, 0.96, 0.05), 2)
    rows = []
    for threshold in thresholds:
        flagged = s >= threshold
        false_positives = int((flagged & ~y).sum())
        missed_loss = float(amt[(~flagged) & y].sum())
        rows.append({
            "threshold": float(threshold),
            "n_flagged": int(flagged.sum()),
            "false_positives": false_positives,
            "fraud_caught": int((flagged & y).sum()),
            "missed_fraud_loss": missed_loss,
            "total_cost": false_positives * review_cost + missed_loss,
        })
    table = pd.DataFrame(rows)
    best = table.loc[table["total_cost"].idxmin()].to_dict()
    return {"table": table, "best": best}


def compute_kris(df: pd.DataFrame, flags: pd.Series) -> dict:
    """Key risk indicators (KRIs) for the card-fraud rule set.

    Fraud rate in basis points, flag rate, false-positive rate,
    fraud loss per $1,000 processed, approval rate, and fraud capture
    — the executive-ready view of risk effectiveness and customer
    impact side by side.
    """
    y = df["is_fraud"].to_numpy().astype(bool)
    f = flags.to_numpy().astype(bool)
    amount = df["amount"].to_numpy(dtype=float)
    total_volume = float(amount.sum())
    fraud_loss = float(amount[y].sum())
    return {
        "n_transactions": int(len(df)),
        "fraud_rate_bps": float(y.mean() * 10_000) if len(df) else 0.0,
        "flag_rate": float(f.mean()) if len(df) else 0.0,
        "false_positive_rate": float((f & ~y).sum() / max((~y).sum(), 1)),
        "fraud_loss_per_1000": float(fraud_loss / total_volume * 1000) if total_volume else 0.0,
        "approval_rate": float(1.0 - f.mean()) if len(df) else 0.0,
        "fraud_capture": float((f & y).sum() / max(y.sum(), 1)),
        "fraud_loss_avoided": float(amount[f & y].sum()),
        "alert_volume": int(f.sum()),
    }


def build_rule_backtesting_section(
    backtest: pd.DataFrame,
    shadow: dict,
    rollout: pd.DataFrame,
    tuned: dict,
    kris: dict,
) -> str:
    """Assemble the plain-text rule-backtesting section for the report."""
    lines = []
    lines.append("")
    lines.append("9. Card-Fraud Rule Backtesting, Shadow Testing, and KRIs")
    lines.append("-" * 70)
    lines.append("Rules backtested on the seeded synthetic test set; the")
    lines.append("challenger set ran in shadow mode (decisions recorded,")
    lines.append("not enforced). Review cost per false positive: $25.")
    lines.append("")
    lines.append("Rule backtest (each rule alone, then all rules combined):")
    header = f"{'Rule':<32}{'Flagged':>9}{'Fraud caught':>13}{'Precision':>11}{'FPs':>7}"
    lines.append(header)
    lines.append("-" * len(header))
    for _, row in backtest.iterrows():
        lines.append(
            f"{row['rule']:<32}{int(row['n_flagged']):>9}"
            f"{int(row['fraud_caught']):>13}{row['precision']:>11.4f}"
            f"{int(row['false_positives']):>7}"
        )
    combined = backtest.iloc[-1]
    lines.append(
        f"Combined set flags {combined['flag_rate']:.2%} of transactions, "
        f"catches {combined['fraud_capture']:.1%} of fraud "
        f"(${combined['fraud_loss_avoided']:,.0f} of fraud loss), "
        f"at {int(combined['false_positives']):,} false positives "
        f"(${combined['review_cost']:,.0f} review cost)."
    )
    lines.append("")
    champ = shadow["champion"]
    chall = shadow["challenger"]
    delta = shadow["deltas"]
    lines.append(
        f"Shadow test — champion ({len(shadow['champion_rules'])} rules) vs "
        f"challenger ({len(shadow['challenger_rules'])} rules): challenger "
        f"catches {int(delta['fraud_caught']):+d} more fraud cases "
        f"({chall['fraud_capture']:.1%} vs {champ['fraud_capture']:.1%} capture) "
        f"for {int(delta['false_positives']):+d} more false positives "
        f"(${delta['review_cost']:+,.0f} review cost) and "
        f"${delta['fraud_loss_avoided']:+,.0f} more fraud loss avoided."
    )
    lines.append("")
    lines.append("Staged rollout of the combined rule set (seeded slices):")
    for _, row in rollout.iterrows():
        lines.append(
            f"  {row['stage_fraction']:.0%} exposure: "
            f"{int(row['n_flagged']):,} flagged, "
            f"{int(row['fraud_caught']):,} fraud caught "
            f"({row['fraud_capture']:.1%} capture), "
            f"{int(row['false_positives']):,} false positives."
        )
    best = tuned["best"]
    lines.append("")
    lines.append(
        f"Score-threshold tuning (false positives vs fraud loss): "
        f"cost-optimal threshold {best['threshold']:.2f} — "
        f"{int(best['false_positives']):,} false positives, "
        f"${best['missed_fraud_loss']:,.0f} missed fraud loss, "
        f"total cost ${best['total_cost']:,.0f}."
    )
    lines.append("")
    lines.append(
        f"KRIs — fraud rate {kris['fraud_rate_bps']:.1f} bps, flag rate "
        f"{kris['flag_rate']:.2%}, false-positive rate "
        f"{kris['false_positive_rate']:.2%}, fraud loss "
        f"${kris['fraud_loss_per_1000']:.2f} per $1,000 processed, "
        f"approval rate {kris['approval_rate']:.2%}, fraud capture "
        f"{kris['fraud_capture']:.1%}."
    )
    return "\n".join(lines)
