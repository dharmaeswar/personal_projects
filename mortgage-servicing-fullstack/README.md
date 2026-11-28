# Mortgage Servicing Full-Stack

A full-stack mortgage loan servicing app: a Spring Boot 3 REST backend and a
React (Vite) frontend. Built as a role project for mortgage-servicing
full-stack roles — ICE Mortgage Technology (Full Stack Developer, Associate
Software Developer) and Rocket Companies Servicing Technology (Software
Engineer I, Req R-083975) — whose stacks are React + Java/Spring Boot or
.NET/C# + GraphQL microservices, PostgreSQL, REST/GraphQL APIs, AWS/EKS
deployments through CI/CD, and AI-assisted development.

**November 2026 update — Upstart Senior Software Engineer, Home Lending:**
the app now also covers the borrower side of home lending — a borrower
application funnel with lending decisioning and a closing workflow — the
application, decisioning, and closing experience the Upstart Home Lending
role builds. See "Borrower application funnel" below.

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

## Borrower application funnel (November 2026 update)

The borrower side of home lending, added for the Upstart Senior Software
Engineer, Home Lending role: an application moves STARTED → SUBMITTED →
APPROVED / CONDITIONAL / DENIED, then APPROVED or CONDITIONAL → CLOSING →
FUNDED. Out-of-order transitions are rejected with HTTP 409; funding is
blocked until every closing-checklist item is complete.

- **Decisioning** (`DecisioningService`, pure and deterministic): DENY when
  credit score < 620, loan-to-value > 0.90, or debt-to-income > 0.50;
  CONDITIONAL when score < 680, LTV > 0.80, or DTI > 0.43; APPROVE
  otherwise. Every rule that fires is returned as a reason, so a denied or
  conditional application always explains itself. These are demo
  underwriting thresholds, not a real lender's policy.
- **Closing checklist:** APPRAISAL, TITLE_SEARCH, HOMEOWNERS_INSURANCE,
  FINAL_DISCLOSURE — all four must be complete before funding.
- **Funnel metrics** (`GET /api/applications/funnel`): counts per stage plus
  conversion rates between stages (submitted, decided, approved, funded), so
  drop-off is visible. The frontend `FunnelPanel` renders this table.
- **Validation:** credit score must be 300–850, amounts must be positive,
  annual income must be greater than zero (DTI divides by it).

| Method | Endpoint | Result |
|---|---|---|
| POST | `/api/applications` | 201 + application (STARTED, with computed LTV and DTI) |
| GET | `/api/applications` | list of applications |
| GET | `/api/applications/{id}` | application, or 404 |
| GET | `/api/applications/funnel` | stage counts + conversion rates |
| POST | `/api/applications/{id}/submit` | SUBMITTED, or 409 |
| POST | `/api/applications/{id}/decide` | APPROVED / CONDITIONAL / DENIED with reasons, or 409 |
| POST | `/api/applications/{id}/closing` | CLOSING, or 409 |
| POST | `/api/applications/{id}/closing/{item}` | checklist item marked done, or 409 / 400 |
| POST | `/api/applications/{id}/fund` | FUNDED, or 409 while the checklist is open |

Tests: 10 `DecisioningServiceTest` cases (approval boundaries, each rule,
multiple deny reasons, LTV/DTI math), 9 `ApplicationServiceTest` cases (full
lifecycle, blocked funding, invalid transitions, funnel math), 6
`ApplicationControllerTest` cases (full funnel through the API, deny reasons,
409/404/400 shapes, funnel endpoint), 3 `FunnelPanel.test.jsx` cases
(counts and rates, empty state, failed request).

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
cd backend && ./run_tests.sh   # builds and runs the 45 backend tests
mvn spring-boot:run            # starts the API on http://localhost:8080
cd ../frontend && npm install && npm test   # 12 frontend tests
npm run dev                    # Vite dev server on :5173, proxies /api to :8080
```

## Deployment on AWS EKS

See `deploy/README.md` for the full flow. In short: multi-stage Dockerfiles
(`deploy/docker/`) build the Spring Boot API and the React/nginx frontend;
Kubernetes manifests (`deploy/k8s/`) run two replicas of each behind
ClusterIP Services, with `GET /api/loans` as the backend health probe and
nginx proxying `/api/` to the backend Service. No live cluster was used;
manifests are YAML-validated and the Dockerfiles reuse the same build
commands the project already runs locally.

## AI-assisted workflow

See `docs/ai-assisted-workflow.md` for how AI tools were used to build this
project: structured prompts, review of every suggestion, and tests proving
each change before it was kept.
