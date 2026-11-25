# GenAI Model Validation Suite

Independent validation harness for a generative-AI decision-support model
— the kind of second-line validation a Model Risk & AI team runs on LLM
and agentic systems before they are approved for use. Built for the
Credit One Bank Risk Modeler III (GenAI Model Validation) role.

All data is synthetic and seeded. No real bank, cardholder, or account
data is used, and nothing here is a claim about any real institution.
No real LLM or API calls: the candidate model is a deterministic
rule-based stand-in with seeded faults, so every run is reproducible
offline. A model-backed generator plugs into the same `generate()`
interface.

## The problem

A GenAI model that explains credit-card account decisions can sound
convincing while citing figures that are not in the source data, flip
its decision when the same prompt is run twice, or drift when the
input mix shifts. This suite validates the model the way SR 26-2 and
OCC Bulletin 2026-13 expect: conceptual soundness, outcomes analysis,
sensitivity and stress testing, stability and drift, explainability,
and a documented verdict with findings.

## What it validates

- **Hallucination / groundedness** (`groundedness.py`): every number an
  explanation cites must appear in the source facts. A cited APR or
  figure with no source match is flagged as a hallucination.
- **Outcomes analysis / benchmarking** (`benchmark.py`): champion
  (GenAI candidate) vs transparent rule challenger vs base-rate
  benchmark, with accuracy and a confusion matrix.
- **Output reliability** (`checks.py`): the same prompt run across
  five seeds; decision agreement and explanation stability (Jaccard
  similarity) are measured. A decision aid must not flip with no
  input change.
- **Sensitivity / stress** (`checks.py`): prompt reordering and
  paraphrase must not flip decisions — the model should react to
  facts, not wording.
- **Stability / drift** (`checks.py`): Population Stability Index
  (PSI) between a reference utilization mix and a stressed mix.
- **Explainability** (`checks.py`): do explanations cite the facts
  that actually drove the decision (utilization, delinquency)?
- **Prompt injection** (`adversarial.py`, new Nov 25, 2026): four
  injection probes — direct instruction override, fake system
  message, instruction buried in retrieved (RAG) text, roleplay
  jailbreak — each run over all 12 cases; a probe compromises a case
  when the decision changes from the clean run. The candidate obeys
  the direct override and the fake system message but resists the
  retrieved-text injection and the jailbreak.
- **Fairness / disparate impact** (`fairness.py`, new Nov 25, 2026):
  approve rate and true-positive rate by synthetic audit cohort
  (6 cases each), disparate-impact ratio against the 0.80
  four-fifths line, and the equal-opportunity gap. Cohorts are audit
  labels only, not real protected attributes; a gap is a signal to
  investigate, not proof of bias.
- **Validation report** (`report.py`): SR 26-2-style findings with
  severity, limitations, release gates, and a PASS/FAIL verdict.

## Run it

```bash
pip install -r requirements.txt
python3 run_validation.py        # writes validation_report.json/.txt
PYTHONPATH=. python3 -m pytest -q tests/
```

Exit code is 0 when the model passes all gates, 1 when it fails any.

## Latest run (12 synthetic cases)

| Check | Result |
| --- | --- |
| Hallucination rate (clean run) | 0.0 |
| Champion accuracy | 1.0 (challenger 1.0, benchmark 0.4167) |
| Mean decision agreement | 0.9167 |
| Sensitivity flip rate | 0.0 |
| Drift PSI (stressed mix) | 8.3712 |
| Explainability coverage | 1.0 |
| Prompt-injection success rate | 0.2917 (14 of 48 attempts) |
| Disparate-impact ratio | 0.6666 (equal-opportunity gap 0.0) |
| **Verdict** | **FAIL — 4 findings** |

Findings the harness caught: **F-02 [High]** — decisions flip across
repeat runs with no input change (seeded misread-utilization fault);
**F-04 [Medium]** — score distribution drift vs reference under the
stressed input mix; **F-07 [High]** — prompt injection changes
decisions (direct override 7/12, fake system message 7/12;
retrieved-text injection and roleplay jailbreak resisted, 0/12 each);
**F-08 [Medium]** — approve-rate gap across audit cohorts
(disparate-impact ratio 0.6666 vs the 0.80 line; 6 cases per cohort,
so investigate before concluding bias). All four are the failures a
validator must surface before a GenAI model is approved for
production use.

## Files

- `genai_validation/data.py` — 12 synthetic credit-card review cases
- `genai_validation/candidate.py` — candidate, challenger, benchmark models
- `genai_validation/groundedness.py` — hallucination detection
- `genai_validation/checks.py` — reliability, sensitivity, PSI drift, explainability
- `genai_validation/adversarial.py` — prompt-injection battery (new Nov 25, 2026)
- `genai_validation/fairness.py` — fairness slices, disparate impact (new Nov 25, 2026)
- `genai_validation/benchmark.py` — champion/challenger/benchmark comparison
- `genai_validation/report.py` — gates, findings, verdict
- `genai_validation/harness.py` — full validation run
- `run_validation.py` — CLI entry point
- `tests/` — 27 tests
