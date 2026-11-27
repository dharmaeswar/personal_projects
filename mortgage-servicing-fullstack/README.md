# Mortgage Servicing Full-Stack

A full-stack mortgage loan servicing app: a Spring Boot 3 REST backend and a
React (Vite) frontend. Built as a role project for ICE Mortgage Technology —
Full Stack Developer (Mortgage Technology) and Associate Software Developer
(Engineer I) — whose stack is React + Java/Spring Boot microservices,
PostgreSQL, REST APIs, and AI-assisted development.

All data is synthetic demo data. There is no ICE affiliation, no real borrower
data, and no production system behind this service.

## What it does

- Create and list mortgage loans (principal, rate, term, start date, escrow).
- Apply monthly payments split into principal, interest, and escrow; extra
  above the scheduled split goes to principal; paying the full balance closes
  the loan.
- Amortization schedule for the remaining term; the final row is adjusted so
  the balance reaches exactly zero.
- Escrow tracking: monthly amount, balance held, next annual analysis date.
- Delinquency check: a loan with no payment within 30 days is flagged.
- Idempotent payments: replaying an idempotency key returns the original
  payment instead of charging twice.

## Money rules (secure coding)

- Money is always `BigDecimal` at scale 2 — `double` is never used for money.
- A payment must at least cover this month's interest + escrow; anything
  below that is rejected with HTTP 422 and leaves the balance untouched.
- Payments on one loan are serialized on the loan lock, so concurrent
  payments cannot corrupt the remaining balance.
- Request validation runs on every write (`jakarta.validation`); bad input
  returns HTTP 400 with per-field errors, never a stack trace.
- Logs never include borrower names, balances, or full loan ids.

## Backend API

| Method | Endpoint | Result |
|---|---|---|
| POST | `/api/loans` | 201 + loan (with computed monthly P&I payment) |
| GET | `/api/loans` | list of loans |
| GET | `/api/loans/{id}` | loan, or 404 |
| POST | `/api/loans/{id}/payments` | payment split, or 422 below minimum due |
| GET | `/api/loans/{id}/payments` | payment history |
| GET | `/api/loans/{id}/schedule` | remaining amortization schedule |
| GET | `/api/loans/{id}/escrow` | escrow monthly, balance, next analysis date |
| GET | `/api/loans/{id}/delinquency?asOf=YYYY-MM-DD` | delinquent true/false |

Worked example: a $300,000 loan at 6.5% over 360 months costs $1,896.20/mo
P&I. The first payment of $2,146.20 ($1,896.20 + $250 escrow) splits into
$1,625.00 interest, $271.20 principal, $250.00 escrow.

## PostgreSQL schema

`backend/src/main/resources/schema.sql` is the deployment DDL: `loans` and
`payments` tables with `NUMERIC(19,2)` money columns and indexes chosen for
the queries the service runs — payment history per loan, idempotency-key
lookup, and the delinquency sweep. The demo service runs on an in-memory
store; the repository interface swaps to Spring Data JPA without touching
the service.

## Run it

```bash
cd backend && ./run_tests.sh   # builds and runs the 20 backend tests
mvn spring-boot:run            # starts the API on http://localhost:8080
cd ../frontend && npm install && npm test   # 9 frontend tests
npm run dev                    # Vite dev server on :5173, proxies /api to :8080
```

## AI-assisted workflow

See `docs/ai-assisted-workflow.md` for how AI tools were used to build this
project: structured prompts, review of every suggestion, and tests proving
each change before it was kept.
