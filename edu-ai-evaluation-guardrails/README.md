# Edu AI Evaluation Guardrails

Evaluation harness for AI tutoring and grading systems in education.
It scores tutor responses with rubric-based automated graders, redacts
personal data before anything is evaluated or logged, records every
run as an observability log, and applies a release gate before a tutor
model version ships.

## What it does

- **Automated graders** (`edu_ai_evaluation_guardrails/graders.py`):
  rubric-based scoring of tutor responses on correctness, clarity,
  encouragement and safety. The built-in grader is a deterministic,
  rule-based stub — no model API calls — so the harness runs offline
  and every score is reproducible. A model-backed grader plugs into
  the same `grade()` interface.
- **Privacy-aware data handling** (`redaction.py`): emails, phone
  numbers, student IDs and known names are redacted from prompts and
  responses *before* grading or logging, and each run reports how
  many redactions were made. A leftover-PII check flags leaks.
- **Reliability and observability** (`harness.py`): each run writes a
  JSONL log (one record per case plus a summary record) with a run id,
  per-criterion scores and redaction counts, so runs can be replayed
  and compared.
- **Release gates** (`gates.py`): explicit thresholds on mean overall
  score, mean correctness, safety failures and PII leaks. The CLI
  exits non-zero when the gate fails, so it can block a release.

## Run it

```bash
python run_evaluation.py
python run_evaluation.py --log my_run.jsonl --min-overall 0.80
```

## Test it

```bash
pytest -q
```

## Honest scope

- All evaluation cases are **synthetic demo data** invented for this
  repo. No real student records, prompts or responses are included.
- The grader is a deterministic stub, not a production LLM judge.
  It demonstrates the harness, the rubric interface and the gate —
  it is not a claim of production LLM or agent deployment.
- Skills used here: Python (standard library only), pytest, JSONL
  logging, regex-based redaction, rubric design, release gating.

## Layout

- `edu_ai_evaluation_guardrails/` — package (redaction, graders,
  harness, gates, synthetic data)
- `run_evaluation.py` — CLI entry point
- `tests/` — pytest suite (redaction, graders, harness, gates)
