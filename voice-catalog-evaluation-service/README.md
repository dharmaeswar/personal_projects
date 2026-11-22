# Voice Catalog & Evaluation Service

A Python service for how customers find, clone, and design AI voices:
a voice catalog (registry, versions, search) plus automated
voice-quality evaluations with pass/fail quality gates, quarantine for
bad versions, eval history, and analytics showing how voices sound
and perform.

Built as a portfolio project for a Software Engineer, Voices
application (voice cloning/design, backend systems that train, store
and serve custom voices, automated evaluations and analytics). All
voices, scores and owners are synthetic demo data; nothing here
describes a real platform, real customers, or a real deployment.
Python standard library only — no third-party runtime dependencies
(pytest is the only dev dependency).

## What it does

- **Voice registry** (`voice_catalog/store.py`) — register voices by
  name, language/locale, style tags, clone source (recording,
  text-prompt, reference-voice) and status (draft / active /
  quarantined); immutable versions per voice; dedup on
  name + language + clone source; validation of locales and clone
  sources; search by name, language, style tag, or status.
- **Evaluation** (`voice_catalog/evaluation.py`) — each eval run scores
  a voice version on intelligibility, similarity to the reference
  voice, latency to first audio, and multilingual coverage, combined
  into a weighted composite (0.35 / 0.35 / 0.15 / 0.15). Quality gates:
  intelligibility ≥ 0.70, similarity ≥ 0.65, latency ≤ 800 ms,
  coverage ≥ 0.80. A run passes only when every gate holds; a
  composite below 0.60 quarantines the voice.
- **Service layer** (`voice_catalog/service.py`) — runs evals, keeps
  eval history per voice, auto-quarantines a voice on a failing
  composite, and summarises analytics: mean scores, pass rate, and
  per-language voice/eval counts.
- **HTTP API** (`voice_catalog/server.py`) — stdlib `http.server` JSON
  API plus a dashboard page; no framework needed.

## Run it

```bash
python -m voice_catalog          # serves http://127.0.0.1:8000
python run_demo.py               # seeds synthetic data, prints the summary
python -m pytest tests/ -q       # 12 tests
```

Example API flow:

```bash
curl -X POST localhost:8000/api/voices \
  -d '{"name":"Mara — Warm Narrator","language":"en-US","style_tags":["warm"],"clone_source":"recording","status":"active"}'
curl -X POST localhost:8000/api/voices/1/versions -d '{"version":"v1"}'
curl -X POST localhost:8000/api/voices/1/evals \
  -d '{"version":"v1","intelligibility":0.92,"similarity":0.88,"latency_ms":420,"coverage":0.95}'
curl localhost:8000/api/voices?language=en-US
curl localhost:8000/api/voices/1/evals
curl localhost:8000/api/analytics
```

## Demo output (actual run of `python run_demo.py`)

4 demo voices (en-US ×2, es-ES, ja-JP) and 5 eval runs:

```
eval voice 1 v2: composite=0.922 passed=True  quarantine=False
eval voice 2 v1: composite=0.866 passed=True  quarantine=False
eval voice 3 v1: composite=0.864 passed=True  quarantine=False
eval voice 2 v1: composite=0.806 passed=False quarantine=False  failed_gates=['similarity 0.58 < 0.65']
eval voice 4 v1: composite=0.47  passed=False quarantine=True   failed_gates=[intelligibility, similarity, latency, coverage]
```

Analytics: 4 voices (3 active, 1 quarantined), 5 eval runs,
pass rate 0.6, mean composite 0.786, mean intelligibility 0.814,
mean similarity 0.708, mean latency 688.0 ms. Per-language:
en-US 2 voices / 3 evals, es-ES 1 voice / 1 eval, ja-JP 1 voice /
1 eval (quarantined). Search checks: `language=en-US` returns Mara
and Theo; `style=calm` returns Lucía; `status=quarantined` returns
Aiko.
