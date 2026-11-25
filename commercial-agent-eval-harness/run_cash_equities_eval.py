#!/usr/bin/env python3
"""Run the Cash Equities client-targeting + RAG evaluation.

Usage:
    python run_cash_equities_eval.py

Prints the ranking and prompt-variant report and writes
cash_equities_eval_report.json. Exits 0 on PASS, 1 on FAIL.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_eval.rag_targeting import (render_cash_equities_report,
                                      run_cash_equities_eval)

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    result = run_cash_equities_eval()
    text = render_cash_equities_report(result)
    print(text, end="")
    with open(os.path.join(HERE, "cash_equities_eval_report.json"), "w") as fh:
        json.dump(result, fh, indent=2)
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
