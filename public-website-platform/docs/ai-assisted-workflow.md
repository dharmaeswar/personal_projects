# AI-assisted workflow

AI tools were used to draft code for this project under the same discipline
used for every role project:

1. Structured prompts stated the exact behavior first (endpoint contract,
   idempotency rule, consent gate), and the AI drafted code against it.
2. Every AI suggestion was read and reviewed before it was kept. Two
   review catches during this build:
   - the first analytics draft flushed the queue even when consent was
     off; the flush now checks consent before sending.
   - the first form draft generated a fresh idempotency key per retry;
     the key is now generated once per submission so retries stay safe.
3. Tests prove each change: 13 backend tests (pytest) and 10 frontend
   tests (Vitest) cover the content API, form validation and idempotency,
   the consent gate, the analytics queue and retry, and the form UI.
   No change was kept without its tests passing.
4. No AI output was shipped unreviewed, and no capability is claimed that
   the code does not have: no Next.js, no TypeScript, no production
   deployment — those gaps are stated in the README and the application
   notes.
