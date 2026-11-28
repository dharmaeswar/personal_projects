"""Deep-learning credit-risk validator: NumPy-only MLP, no sklearn needed."""
import numpy as np

from dl_credit.data import (NUMERIC_FEATURES, TEXT_KEYWORDS, feature_matrix,
                            generate, standardize, time_split)
from dl_credit.mlp import MLPClassifier
from dl_credit.challengers import BaseRateModel, LogisticRegression
from dl_credit.metrics import outcomes_summary
from dl_credit.validation import (data_integrity, drift_report,
                                  permutation_importance, vintage_backtest)
from dl_credit.report import build_report, render_text, write_report
from dl_credit.segments import segment_summary


def main():
    df = generate()
    train, val, test = time_split(df)
    Xtr, names = feature_matrix(train)
    Xva, _ = feature_matrix(val)
    Xte, _ = feature_matrix(test)
    Xtr_s, mean, std = standardize(Xtr, Xtr)
    Xva_s = (Xva - mean) / std
    Xte_s = (Xte - mean) / std
    ytr, yva, yte = (train["defaulted"].to_numpy(), val["defaulted"].to_numpy(),
                     test["defaulted"].to_numpy())

    mlp = MLPClassifier(hidden=(32, 16), lr=0.05, epochs=300, patience=25)
    mlp.fit(Xtr_s, ytr, Xva_s, yva)
    # Re-fit determinism check: same seed must reproduce the same scores.
    mlp2 = MLPClassifier(hidden=(32, 16), lr=0.05, epochs=300, patience=25)
    mlp2.fit(Xtr_s, ytr, Xva_s, yva)
    max_diff = float(np.max(np.abs(mlp.predict_proba(Xte_s)
                                   - mlp2.predict_proba(Xte_s))))
    print("Implementation reproduction: max score diff on re-fit: %.6f" % max_diff)

    logreg = LogisticRegression(lr=0.1, epochs=500)
    logreg.fit(Xtr_s, ytr)
    base = BaseRateModel().fit(Xtr_s, ytr)

    cand = outcomes_summary(yte, mlp.predict_proba(Xte_s))
    chal = outcomes_summary(yte, logreg.predict_proba(Xte_s))
    bench = outcomes_summary(yte, base.predict_proba(Xte_s))
    backtest = vintage_backtest(test, mlp.predict_proba(Xte_s))
    # "Later" population for drift: the validation split, scored later.
    drift = drift_report(train, val, mlp.predict_proba(Xtr_s),
                         mlp.predict_proba(Xva_s), NUMERIC_FEATURES)
    integrity = data_integrity(df)
    importance, base_auc = permutation_importance(mlp, Xte_s, yte, names)
    # Segment backtest: k-means clusters on the standardised numeric
    # features of the test population, calibrated segment by segment.
    segments, inertia = segment_summary(
        Xte_s[:, :len(NUMERIC_FEATURES)], test, mlp.predict_proba(Xte_s))
    print("Segment clustering: k=4, inertia %.1f" % inertia)

    report = build_report(cand, chal, bench, backtest, drift, integrity,
                          importance, len(train), len(test),
                          segments=segments)
    report["epochs_run"] = mlp.n_epochs_run_
    report["reproduction_max_diff"] = max_diff
    write_report(report, "validation_report.txt", "validation_report.json")
    print(render_text(report))
    print("MLP trained for %d epochs (early stopping patience 25)." % mlp.n_epochs_run_)


if __name__ == "__main__":
    main()
