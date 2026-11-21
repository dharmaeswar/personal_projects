# Claim Document Synthesis

A portfolio project for a **Senior Software Engineer, Medhub / AI Insurance SaaS** role (EvolutionIQ-style). It builds the backend of a multi-tenant enterprise SaaS claims application: raw claim narratives become structured facts, a drafted claim synthesis, and — when the extraction is uncertain — a human-in-the-loop review task.

**All data is synthetic and seeded.** No real claimant, medical, or insurance data is used, and nothing here is a claim about any real company.

## Problem statement

Claims professionals need fast, accurate claim syntheses — who was hurt, how, when, where they were treated, and for how much — but the source material is free-text narratives: producers write dates and amounts in different formats, injury wording varies, and some documents are missing key facts entirely. Trusting an automated read of a bad document means paying the wrong claim.

This project fixes that with a claims pipeline:

- **Fact extraction** — injury type, body part, incident date, treatment provider, and claimed amount are pulled from each narrative with a per-fact confidence score. Strong matches score 1.0; weak matches (e.g. an unknown clinic name) score 0.6; missing facts score 0.0.
- **Synthesis** — a deterministic, template-based summary states exactly which facts it used and flags anything missing or low-confidence. It never invents a value. The summary records its source (`template`) so reviewers can tell machine-drafted text from human-confirmed facts — this is the seam where an LLM call would plug in.
- **Human-in-the-loop review** — any document whose mean fact confidence falls below 0.8 goes to the review queue instead of being trusted. A reviewer can approve the facts as extracted, correct individual facts, or reject the document with a reason. Every decision lands in an append-only audit log with actor and timestamp.
- **Multi-tenancy** — every claim carries a `tenant_id`; reads, listings, and review decisions are tenant-scoped, and cross-tenant access is refused with a 403 instead of leaking another tenant's data.
- **REST API** — a standard-library-only HTTP service (`claim_synthesis/api.py`) exposes ingest, lookup, listing, review-queue, and review-decision endpoints as JSON.

## Layout

```
claim_synthesis/
  documents.py    seeded synthetic claim documents + tenant registry
  extraction.py   rule-based fact extraction with confidence scores
  synthesis.py    template-based claim summary (never invents values)
  review.py       HITL review queue + append-only audit log
  store.py        tenant-scoped in-memory claim store
  service.py      orchestration: ingest -> extract -> synthesize -> queue
  api.py          stdlib HTTP API (POST /claims, GET /claims, review endpoints)
run_demo.py       end-to-end demo: seed -> ingest -> report
tests/            pytest suite (extraction, synthesis, service, tenancy, API)
```

## Run it

```bash
pip install -r requirements.txt
python run_demo.py
python -m pytest -q
python -m claim_synthesis.api --port 8000 --seed
```

`run_demo.py` ingests 27 seeded documents (24 complete + 3 deliberately incomplete) and reports how many were trusted vs queued for review. The three incomplete documents exercise the review queue on every run.

## Design notes

- Extraction is rule-based and deterministic on purpose: the behaviour that matters (confidence scoring, review routing, tenant isolation, audit) is testable without an LLM API key or network access.
- A corrected fact is stored with confidence 1.0 and the correcting reviewer, so the audit trail shows what the machine read and what the human changed.
- The API uses only the Python standard library, so the service runs anywhere with no third-party install beyond pytest.
