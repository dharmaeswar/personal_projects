#!/usr/bin/env python3
"""Batch vol-surface checker -- thin wrapper around the package CLI.

Replaces the manual, by-hand surface checks analysts used to run: point it
at a surface CSV and it runs every arbitrage/consistency check, writes a
violations report and emits an alert for each failure.

Example::

    python run_checks.py data/sample_surface.csv --report violations.json
"""

from vol_surface_checker.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
