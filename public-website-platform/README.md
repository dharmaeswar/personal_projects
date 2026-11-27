# Public Website Platform

A full-stack public website platform: a React frontend serving content
pages, a consent banner, and a contact form; a Python API behind it for
content, form submissions, analytics events, and consent records.

Built as a role project for Vercel — Software Engineer, Website — whose
work spans React and Next.js applications, shared libraries, APIs, and the
services that power forms, analytics, content, and more, with performance,
accessibility, and consent behavior as first-class concerns.

All data is synthetic demo data. There is no Vercel affiliation, no real
visitor data, and no production system behind this service.

## What it does

Backend (Python standard library only, no web framework):

- `GET /api/content/pages` — list pages; `GET /api/content/pages/{slug}` —
  page blocks (hero, text) served like a small CMS read API.
- `POST /api/forms/{form_id}/submissions` — validates required fields and
  email format; an `Idempotency-Key` header is required, and replaying a
  key returns the original submission instead of storing a duplicate.
- `POST /api/analytics/events` — batch event intake (max 50 per batch);
  rejected with 403 unless the visitor granted analytics consent, so no
  event is ever stored before consent.
- `GET /api/consent?visitor_id=...` / `POST /api/consent` — per-visitor
  analytics/marketing consent record; analytics defaults to off.
- `GET /health` — liveness. `GET /metrics` — Prometheus-format text:
  request counts by method/path/status and total analytics events.

Frontend (React 18 + Vite):

- `PageContent` renders content blocks fetched from the API.
- `ConsentBanner` keeps analytics off until the visitor explicitly accepts.
- `ContactForm` validates on the client, then posts with retries and one
  idempotency key, so a double-click or a retried request never duplicates
  a submission; server 400s surface per-field messages.
- `lib/analytics.js` is a consent-gated event queue: events tracked before
  consent are dropped, accepted events batch up and flush every 5 seconds
  (or at 10 events), and a failed flush keeps the events for the next try.

## Skills used

Only skills Dharma has verified: Python, JavaScript, React, HTML, CSS,
REST APIs, JSON, pytest, Vitest, Linux, Git. This project does **not**
claim Next.js, TypeScript, or a production Vercel deployment — the frontend
is React 18 with Vite, the backend is Python standard library, and the
analytics endpoint only stores events in memory. Those gaps are stated
plainly in the application notes.

## Run it

```bash
python3 run_service.py            # API on http://127.0.0.1:8000
cd backend && python3 -m pytest tests/   # 13 backend tests
cd ../frontend && npm install && npm test  # 10 frontend tests
npm run dev                        # Vite dev server on :5173, proxies /api to :8000
```

## AI-assisted workflow

See `docs/ai-assisted-workflow.md` for how AI tools were used to build this
project: structured prompts, review of every suggestion, and tests proving
each change before it was kept.
