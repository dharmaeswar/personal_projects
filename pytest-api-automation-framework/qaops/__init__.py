"""QA/DevOps helpers for business-systems releases.

Two small tools that sit on top of the pytest API framework:

- ``health``: probe an environment's HTTP endpoints (health, readiness,
  version) and validate required configuration before a release is
  promoted. Every check returns a structured result; nothing here
  assumes a specific vendor API.
- ``gate``: turn a pytest result summary into a release-gate decision.
  A release passes only when the pass rate, the failure count and the
  required checks all meet their thresholds. The gate report is JSON
  so a CI job can consume it directly.
"""
