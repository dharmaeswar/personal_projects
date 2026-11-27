# Run the claims pipeline (tests + full load) from PowerShell.
# Usage: from the project root, run: powershell -File scripts/run_pipeline.ps1
# Uses the Python on PATH; pass -Python to point at a venv python instead.
param([string]$Python = "python")

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { Write-Error "tests failed"; exit $LASTEXITCODE }

& $Python run_pipeline.py
if ($LASTEXITCODE -ne 0) { Write-Error "pipeline failed"; exit $LASTEXITCODE }

Write-Host "Pipeline OK: bronze -> silver -> gold + ML scores written under lakehouse/"
