"""IFRS 9 / CECL expected credit loss (ECL) validation toolkit.

Standard library only. Implements:

- IFRS 9 staging (Stage 1 / 2 / 3) with significant-increase-in-credit-risk
  (SICR) triggers: 30+ days past due, or a credit-score drop of 100+ points.
- 12-month ECL for Stage 1 and lifetime ECL for Stage 2 / 3, from
  PD x LGD x EAD.
- CECL lifetime ECL for every loan.
- Back-testing of predicted ECL against realised losses.
- Challenger-model benchmarking (score-band PD model vs primary PD model).
- Portfolio monitoring report with breach flags.

All inputs are validated: PD and LGD must sit in [0, 1], balances must be
non-negative, and Stage 3 loans carry a lifetime PD of 1.0 by definition.
"""

from dataclasses import dataclass

STAGE_1 = 1
STAGE_2 = 2
STAGE_3 = 3

# SICR / default triggers (IFRS 9 backstops).
SICR_DPD_THRESHOLD = 30
DEFAULT_DPD_THRESHOLD = 90
SICR_SCORE_DROP = 100

# Monitoring tolerances.
STAGE_2_SHARE_LIMIT = 0.20
STAGE_3_SHARE_LIMIT = 0.05
COVERAGE_LOW = 0.80
COVERAGE_HIGH = 1.25
TOP10_ECL_SHARE_LIMIT = 0.50


@dataclass
class Loan:
    """One loan in the synthetic portfolio.

    balance is the exposure at default (EAD). pd_12m / pd_lifetime are the
    12-month and lifetime probabilities of default. lgd is loss given
    default as a fraction of EAD.
    """

    loan_id: str
    balance: float
    pd_12m: float
    pd_lifetime: float
    lgd: float
    days_past_due: int = 0
    credit_score_now: int = 700
    credit_score_orig: int = 700
    defaulted: bool = False

    def __post_init__(self):
        if self.balance < 0:
            raise ValueError("balance (EAD) must be non-negative")
        for name in ("pd_12m", "pd_lifetime", "lgd"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1], got {value}")
        if self.pd_lifetime < self.pd_12m:
            raise ValueError("pd_lifetime must be >= pd_12m")
        if self.days_past_due < 0:
            raise ValueError("days_past_due must be non-negative")


def classify_stage(loan):
    """IFRS 9 stage for a loan.

    Stage 3: defaulted, or 90+ days past due.
    Stage 2: SICR — 30+ days past due, or credit score down 100+ points.
    Stage 1: everything else (no significant increase in credit risk).
    """
    if loan.defaulted or loan.days_past_due >= DEFAULT_DPD_THRESHOLD:
        return STAGE_3
    if loan.days_past_due >= SICR_DPD_THRESHOLD:
        return STAGE_2
    if loan.credit_score_orig - loan.credit_score_now >= SICR_SCORE_DROP:
        return STAGE_2
    return STAGE_1


def ecl_ifrs9(loan):
    """IFRS 9 ECL: 12-month ECL in Stage 1, lifetime ECL in Stages 2 and 3."""
    stage = classify_stage(loan)
    if stage == STAGE_1:
        return loan.pd_12m * loan.lgd * loan.balance
    if stage == STAGE_3:
        return 1.0 * loan.lgd * loan.balance
    return loan.pd_lifetime * loan.lgd * loan.balance


def ecl_cecl(loan):
    """CECL ECL: lifetime ECL for every loan, whatever its stage."""
    return loan.pd_lifetime * loan.lgd * loan.balance


def challenger_ecl(loan):
    """Challenger model ECL.

    A simpler score-band model: the PD comes from a fixed table keyed on the
    current credit score instead of the loan-level modelled PD. Used only to
    benchmark the primary model, never as the reported ECL.
    """
    score = loan.credit_score_now
    if score >= 720:
        pd_band = 0.005
    elif score >= 660:
        pd_band = 0.02
    elif score >= 600:
        pd_band = 0.06
    elif score >= 540:
        pd_band = 0.15
    else:
        pd_band = 0.30
    return pd_band * loan.lgd * loan.balance


def portfolio_ecl(loans):
    """Portfolio totals: ECL by stage, IFRS 9 total, CECL total, counts."""
    by_stage = {STAGE_1: 0.0, STAGE_2: 0.0, STAGE_3: 0.0}
    counts = {STAGE_1: 0, STAGE_2: 0, STAGE_3: 0}
    cecl_total = 0.0
    for loan in loans:
        stage = classify_stage(loan)
        by_stage[stage] += ecl_ifrs9(loan)
        counts[stage] += 1
        cecl_total += ecl_cecl(loan)
    return {
        "by_stage": by_stage,
        "counts": counts,
        "total_loans": len(loans),
        "total_balance": sum(loan.balance for loan in loans),
        "ifrs9_total": sum(by_stage.values()),
        "cecl_total": cecl_total,
    }


def backtest(loans, realised_loss):
    """Back-test predicted IFRS 9 ECL against realised losses.

    realised_loss maps loan_id -> realised loss amount. Returns the coverage
    ratio (predicted / realised), mean absolute error per loan, the number of
    loans where realised loss exceeded predicted ECL, and a breach flag when
    coverage sits outside [0.80, 1.25].
    """
    predicted = sum(ecl_ifrs9(loan) for loan in loans)
    realised = sum(realised_loss.get(loan.loan_id, 0.0) for loan in loans)
    errors = [
        abs(ecl_ifrs9(loan) - realised_loss.get(loan.loan_id, 0.0))
        for loan in loans
    ]
    mae = sum(errors) / len(errors) if errors else 0.0
    under_predicted = sum(
        1
        for loan in loans
        if realised_loss.get(loan.loan_id, 0.0) > ecl_ifrs9(loan)
    )
    coverage = predicted / realised if realised > 0 else float("inf")
    return {
        "predicted_ecl": predicted,
        "realised_loss": realised,
        "coverage_ratio": coverage,
        "mae_per_loan": mae,
        "under_predicted_loans": under_predicted,
        "breach": not (COVERAGE_LOW <= coverage <= COVERAGE_HIGH),
    }


def benchmark(loans, realised_loss):
    """Benchmark primary vs challenger model on realised losses.

    Compares mean absolute error per loan for each model and names the model
    with the lower error. Both models are scored on the same realised losses.
    """
    primary_errors = [
        abs(ecl_ifrs9(loan) - realised_loss.get(loan.loan_id, 0.0))
        for loan in loans
    ]
    challenger_errors = [
        abs(challenger_ecl(loan) - realised_loss.get(loan.loan_id, 0.0))
        for loan in loans
    ]
    n = len(loans) or 1
    primary_mae = sum(primary_errors) / n
    challenger_mae = sum(challenger_errors) / n
    return {
        "primary_mae": primary_mae,
        "challenger_mae": challenger_mae,
        "winner": "primary" if primary_mae <= challenger_mae else "challenger",
        "mae_gap": abs(primary_mae - challenger_mae),
    }


def monitoring_report(loans, realised_loss):
    """Monitoring report: stage mix, coverage, concentration, breach flags.

    Flags fire when the Stage 2 share tops 20%, the Stage 3 share tops 5%,
    back-test coverage sits outside [0.80, 1.25], or the top 10 loans by ECL
    hold over 50% of total ECL.
    """
    totals = portfolio_ecl(loans)
    test = backtest(loans, realised_loss)
    n = totals["total_loans"] or 1
    stage2_share = totals["counts"][STAGE_2] / n
    stage3_share = totals["counts"][STAGE_3] / n
    ranked = sorted(loans, key=ecl_ifrs9, reverse=True)
    top10_ecl = sum(ecl_ifrs9(loan) for loan in ranked[:10])
    top10_share = top10_ecl / totals["ifrs9_total"] if totals["ifrs9_total"] else 0.0
    flags = []
    if stage2_share > STAGE_2_SHARE_LIMIT:
        flags.append(f"stage2_share {stage2_share:.1%} above {STAGE_2_SHARE_LIMIT:.0%} limit")
    if stage3_share > STAGE_3_SHARE_LIMIT:
        flags.append(f"stage3_share {stage3_share:.1%} above {STAGE_3_SHARE_LIMIT:.0%} limit")
    if test["breach"]:
        flags.append(f"coverage_ratio {test['coverage_ratio']:.2f} outside [0.80, 1.25]")
    if top10_share > TOP10_ECL_SHARE_LIMIT:
        flags.append(f"top10_ecl_share {top10_share:.1%} above {TOP10_ECL_SHARE_LIMIT:.0%} limit")
    return {
        "stage2_share": stage2_share,
        "stage3_share": stage3_share,
        "coverage_ratio": test["coverage_ratio"],
        "top10_ecl_share": top10_share,
        "flags": flags,
        "breach": bool(flags),
    }
