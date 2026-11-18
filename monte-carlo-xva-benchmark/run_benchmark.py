#!/usr/bin/env python3
"""Run the Monte-Carlo XVA benchmark from the project root.

Equivalent to ``python -m xva_benchmark``; see ``--help`` for options.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xva_benchmark.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
