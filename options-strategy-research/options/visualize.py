"""Small text/CSV visualisations for research output.

No plotting dependency: payoff diagrams render as ASCII, and the P&L
series exports as CSV for a spreadsheet or notebook.
"""

import csv
import os


def ascii_payoff(legs, low, high, steps=40, width=60, height=15):
    """ASCII payoff diagram for a strategy over an underlying-price range."""
    from .strategies import strategy_payoff

    spots = [low + (high - low) * i / (steps - 1) for i in range(steps)]
    pnls = [strategy_payoff(legs, s) for s in spots]
    top = max(pnls + [0.0])
    bottom = min(pnls + [0.0])
    span = top - bottom or 1.0
    rows = []
    for row in range(height):
        level = top - span * row / (height - 1)
        line = ""
        for pnl in pnls:
            if abs(pnl - level) <= span / (height - 1) / 2.0:
                line += "*"
            elif level == 0.0:
                line += "-"
            else:
                line += " "
        rows.append(f"{level:8.2f} |{line}")
    axis = " " * 8 + " +" + "-" * width
    label = (f" {' ' * 8}  underlying {low:.0f} -> {high:.0f} "
             f"(max loss {min(pnls):.2f}, max gain {max(pnls):.2f})")
    return "\n".join(rows + [axis, label])


def write_pnl_csv(pnl_series, path):
    """Write a daily P&L series to CSV with day and cumulative P&L."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["day", "pnl"])
        for day, pnl in enumerate(pnl_series):
            writer.writerow([day, round(pnl, 4)])
    return path
