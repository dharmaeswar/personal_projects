#!/usr/bin/env python3
"""Convenience wrapper: ``python run_validation.py [--config ...] [--out-dir ...]``.

Equivalent to ``python -m model_validation_suite``.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from model_validation_suite.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
