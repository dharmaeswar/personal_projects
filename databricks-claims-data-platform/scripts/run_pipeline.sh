#!/usr/bin/env bash
# Run the claims pipeline (tests + full load) from Bash.
# Usage: from the project root, run: bash scripts/run_pipeline.sh
# Uses the Python on PATH; set PYTHON to point at a venv python instead.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
"$PYTHON" -m pytest -q
"$PYTHON" run_pipeline.py
echo "Pipeline OK: bronze -> silver -> gold + ML scores written under lakehouse/"
