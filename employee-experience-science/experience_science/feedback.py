"""Open-ended feedback theme classification and benchmark.

A transparent keyword classifier assigns each feedback comment to one
theme (workload, schedule, manager, pay, growth, tools). It is then
scored against the known true theme with per-theme precision/recall/F1
and macro F1 — the same benchmark discipline used to evaluate a GenAI
feedback-summarisation model, but with a rule-based baseline so the
benchmark itself can be checked end to end.
"""

import re

KEYWORDS = {
    "workload": ["workload", "overtime", "too many hours", "too heavy", "unmanageable", "more people"],
    "schedule": ["schedule", "shift change", "rotating", "unpredictable", "notice", "childcare"],
    "manager": ["manager", "managers", "feedback on my performance", "direction", "listen"],
    "pay": ["pay", "raise", "too low"],
    "growth": ["grow", "promoted", "training", "career growth", "next steps"],
    "tools": ["tools", "crash", "scanners", "software", "system is slow", "outdated"],
}


def classify(text):
    text = text.lower()
    best_theme, best_hits = None, 0
    for theme, words in KEYWORDS.items():
        hits = sum(1 for w in words if re.search(r"\b" + re.escape(w) + r"\b", text))
        if hits > best_hits:
            best_theme, best_hits = theme, hits
    return best_theme or "unknown"


def benchmark(rows):
    themes = list(KEYWORDS)
    counts = {t: {"tp": 0, "fp": 0, "fn": 0} for t in themes}
    correct = 0
    for r in rows:
        pred = classify(r["feedback_text"])
        true = r["feedback_theme"]
        if pred == true:
            correct += 1
            counts[true]["tp"] += 1
        else:
            if pred in counts:
                counts[pred]["fp"] += 1
            counts[true]["fn"] += 1
    per_theme = {}
    for t in themes:
        tp, fp, fn = counts[t]["tp"], counts[t]["fp"], counts[t]["fn"]
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_theme[t] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "support": tp + fn,
        }
    macro_f1 = sum(v["f1"] for v in per_theme.values()) / len(per_theme)
    return {
        "accuracy": round(correct / len(rows), 3),
        "macro_f1": round(macro_f1, 3),
        "per_theme": per_theme,
    }
