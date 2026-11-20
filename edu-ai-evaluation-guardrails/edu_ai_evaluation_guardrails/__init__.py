"""Edu AI Evaluation Guardrails.

Evaluation harness for AI tutoring and grading systems in education:
rubric-based automated graders, privacy-aware handling of institutional
data (PII redaction before any evaluation), observability logging of
evaluation runs, and release-gate decisions before a tutor model ships.

All data in this repo is synthetic demo data. No real student records,
no real model API calls: the grader interface is deterministic and
stub-based so the harness can be tested end to end offline.
"""

__version__ = "1.0.0"
