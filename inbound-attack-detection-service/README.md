# Inbound Attack Detection Service

A small backend service that scores synthetic inbound email messages for
attack risk (phishing / business-email-compromise / spoof), evaluates the
classifier statistically, and triages flagged messages with a
deterministic simulated agent.

Built as a portfolio project for a Software Engineer II, Attack Detection
application (backend services, data pipelines, ML/LLM integration into
detection workflows, statistical evaluation of classifiers).

## What it does

1. **Feature extraction** (`detection/features.py`) — sender-domain
   mismatch, display-name spoofing against a known-exec list, reply-to
   mismatch, lookalike (typosquat) domains via edit distance, URL count /
   suspicious TLDs / IP hosts, risky attachments, urgency keywords, and
   SPF/DKIM/DMARC pass-fail flags.
2. **Scoring** (`detection/classifier.py`) — a deterministic,
   explainable weighted-score model. Every prediction lists its top
   contributing features. `train()` calibrates the decision threshold by
   maximising F1 on a labelled training split; the weights themselves are
   hand-set priors, not learned.
3. **Evaluation** (`detection/evaluation.py`) — confusion matrix,
   precision, recall, F1 and ROC-AUC computed from scratch (no
   scikit-learn), per-segment slices (phishing vs BEC vs legitimate bulk),
   and a threshold sweep table.
4. **Triage agent** (`detection/triage.py`) — a deterministic simulation
   of an agentic triage workflow: gather signals → check allow/block
   lists → apply a decision policy → verdict (`quarantine` / `allow` /
   `escalate`) with rationale. Same input always gives the same verdict.
5. **Pipeline** (`detection/pipeline.py`) — ingest synthetic messages →
   normalise → score → store in SQLite → write a JSON report.
6. **Service** (`detection/service.py`) — stdlib `http.server` backend
   with `POST /score`, `POST /triage` and `GET /health`.

## How to run

```bash
pip install -r requirements.txt   # pytest only
python -m pytest -q               # 46 tests
python run_detection.py           # writes detection_report.json + detection_results.db
python -m detection.service       # serves http://127.0.0.1:8000
```

Example request:

```bash
curl -X POST localhost:8000/score -H 'Content-Type: application/json' -d '{
  "sender": "sarah chen@acmecorp-support.xyz",
  "display_name": "Sarah Chen",
  "reply_to": "support@acmec0rp.com",
  "subject": "URGENT: Verify your account immediately",
  "body": "Verify your account immediately at https://acme-secure-login.xyz/verify.",
  "spf_pass": false, "dkim_pass": false, "dmarc_pass": false
}'
```

## Results from a real run

Seeded synthetic dataset, 150 messages (60 legitimate, 40 phishing,
25 BEC, 25 legitimate bulk). Threshold 0.35, calibrated by F1 on a
100-message train split:

| Metric | Value |
|---|---|
| Precision | 1.000 |
| Recall | 1.000 |
| F1 | 1.000 |
| ROC-AUC | 1.000 |
| Confusion matrix | TP=65, FP=0, TN=85, FN=0 |

Per-segment F1: phishing 1.000, BEC 1.000. (Legitimate and bulk segments
contain no attack labels, so precision/recall are 0 by definition there —
an artefact of the metric, not a failure.)

Triage verdicts on the 65 flagged messages: 65 quarantine, 0 escalate,
0 allow.

## Honest limits

- **All data is synthetic and seeded.** No real emails, no real
  credentials, no real LLM or API calls anywhere in this project.
- **The scorer is rules + from-scratch statistics, not production
  detection science.** Weights are hand-set priors; only the threshold is
  fitted. The perfect 1.000 scores above say the synthetic classes are
  cleanly separable by design — they say nothing about performance on
  real mail, where precision/recall trade-offs are far harder.
- **The triage "agent" is a deterministic simulation, not a real LLM.**
  Its steps are fixed policy code; it cannot reason about novel attacks.
- **Evaluation is in-sample-adjacent:** the threshold is calibrated on
  part of the same synthetic distribution it is evaluated on.
- Nothing here is a claim about any employer's systems or about the
  author's work history; it is a self-contained demo built from scratch.

## Project layout

```
detection/
  features.py     feature extraction
  classifier.py   weighted scorer + threshold calibration
  evaluation.py   confusion matrix / P-R / F1 / ROC-AUC from scratch
  triage.py       deterministic triage agent
  pipeline.py     synthetic data + ingest/score/store/report
  service.py      http.server backend (POST /score, POST /triage)
run_detection.py  CLI entry point
tests/            46 pytest tests
```
