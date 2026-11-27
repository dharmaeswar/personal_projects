# AI-assisted workflow

How AI tools were used to build this project, and what was checked by hand.

## What the AI did

- Drafted the Spring Boot service, controller, and repository from a short
  brief: mortgage servicing, P&I + escrow payments, amortization schedule,
  idempotent payments.
- Drafted the React components (loan list, payment form, amortization table)
  and the pure amortization math in `frontend/src/lib/amortization.js`.
- Drafted the first versions of the JUnit/MockMvc and Vitest suites.

## What was reviewed and proven, not taken on trust

- Every money formula was checked against an independent calculation: the
  $300,000 / 6.5% / 360-month payment ($1,896.20) and the first-month split
  ($1,625.00 interest, $271.20 principal) were computed with Python's
  `decimal` module before the tests were written, and the tests pin those
  values.
- The schedule test proves the principal column sums to the original balance
  and the last row reaches exactly zero — a formula error would fail it.
- The concurrency test proves ten simultaneous payments leave the balance
  consistent with the recorded principal portions.
- The frontend minimum-due test proves a short payment is refused in the UI
  before it reaches the API; the backend test proves the same refusal with
  HTTP 422.
- A real defect was found and fixed during review: the payment form's native
  `min=` attribute blocked submission before the app's own validation ran,
  so the error message never appeared. The attribute was removed; the JS
  check and the backend 422 are the guards.
- The build itself was run end to end: `mvn test` (20 tests) and
  `npm test` (9 tests) plus `npm run build`, all passing.

## What the AI did not do

- No production data, borrower data, or employer system was touched. All
  data is synthetic.
- No AI output was committed without a passing test proving the behaviour it
  claimed.
