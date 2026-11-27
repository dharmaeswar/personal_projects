# Spring Boot REST Banking API

A Spring Boot 3 REST service for retail banking account operations, built as a role
project for a Java / Spring Boot Software Engineer role (Bank of America, Software
Engineer I – Java). It covers the JD's core stack: Java 17, Spring Boot, REST services,
JUnit 5, JSON, Git, and CI/CD (GitHub Actions), plus the secure-coding and AI-assisted
engineering practices the posting asks for.

The API-routing and observability layer below was added for the Oracle OCI SPLAT
Core Infrastructure Engineer 2 role (Job 342848): request-path services, traffic
management, and operational controls for high-throughput Java services.

All data is synthetic demo data. There is no Bank of America affiliation, no real
account data, and no production system behind this service.

## What it does

- Create, list, and fetch accounts (`CHECKING` / `SAVINGS`) with an opening balance.
- Deposit and withdraw with validation; withdrawals that exceed the balance are
  rejected with HTTP 422 and leave the balance untouched.
- Transfer between accounts with an idempotency key: replaying the same key returns
  the original result instead of moving money twice.
- Transaction history per account.

## Money rules (secure coding)

- Money is always `BigDecimal` at scale 2 — `double` is never used for money.
- Transfers lock both accounts in id order, so opposite-direction concurrent
  transfers cannot deadlock; a self-transfer is rejected.
- Request validation runs on every write (`jakarta.validation`); bad input returns
  HTTP 400 with per-field errors, never a stack trace.
- Logs never include balances, owner names, or full account ids.

## API

| Method | Endpoint | Body | Result |
|---|---|---|---|
| POST | `/api/accounts` | `{"ownerName","accountType":"CHECKING\|SAVINGS","openingBalance"}` | 201 + account |
| GET | `/api/accounts` | — | list of accounts |
| GET | `/api/accounts/{id}` | — | account, or 404 |
| POST | `/api/accounts/{id}/deposit` | `{"amount","memo?"}` | updated account |
| POST | `/api/accounts/{id}/withdraw` | `{"amount","memo?"}` | updated account, or 422 |
| POST | `/api/accounts/{id}/transfer` | `{"toAccountId","amount","idempotencyKey?"}` | source account |
| GET | `/api/accounts/{id}/transactions` | — | transaction history |

Error responses share one shape: `{"status","error","details","timestamp"}`.

## API routing & observability layer

Every request passes through two filters, registered in `gateway/GatewayConfig.java`:

- `RequestContextFilter` — echoes an incoming `X-Request-Id` or generates one, returns
  it on the response, records per-route counts and latency in `RequestMetrics`, and logs
  one structured line per request (`method path status latency_ms request_id`) so a defect
  can be traced from a log line back to one request.
- `RateLimitFilter` — a per-client token-bucket limiter (`X-Client-Id` header, or remote
  address when absent). Over the limit it returns HTTP 429 with the same JSON error shape.
  Default 100 requests per client per minute (`app.rate-limit.per-minute`).

Operations endpoints (`ops/OpsController.java`):

| Method | Endpoint | Result |
|---|---|---|
| GET | `/ops/health` | `{"status":"UP"}` — used for deployment validation |
| GET | `/ops/metrics` | total requests, average latency, counts by route and status |

## Run it

```bash
./run_tests.sh        # builds and runs the full test suite
mvn spring-boot:run   # starts the API on http://localhost:8080
```

Requires Java 17+ and Maven 3.9+.

Example:

```bash
curl -X POST localhost:8080/api/accounts \
  -H 'Content-Type: application/json' \
  -d '{"ownerName":"Ada Lovelace","accountType":"CHECKING","openingBalance":250.00}'
```

## Tests

`mvn test` — 23 tests, all passing:

- `AccountServiceTest` (10 tests): opening-balance rules, deposit/withdraw, overdraft
  rejection with unchanged balance, exact-balance withdrawal, transfer legs and
  balances, overdraft/self-transfer rejection, idempotent replay (money moves once),
  unknown-account handling, and a 20-thread concurrent-deposit race that loses no money.
- `AccountControllerTest` (7 tests, MockMvc): create/get flow, deposit/withdraw/history
  flow, transfer between accounts, 422 overdraft with error body, 404 unknown account,
  400 validation errors (3 field errors), and a rejected zero deposit.
- `RateLimiterTest` (2 tests): capacity is enforced, and limits are per client.
- `GatewayFiltersTest` (4 tests, MockMvc): request-id echo and generation, 429 after the
  per-client limit, health `UP`, and metrics counting requests.

## CI / quality

- `.github/workflows/ci.yml` — GitHub Actions: Java 17, `mvn -B test`, on every push
  and pull request.
- SonarQube is the code-quality gate named in the JD; the build keeps the code
  SonarQube-clean by design (no duplicated money logic, no `double` money, no
  swallowed exceptions, no secrets), and the workflow has a commented SonarQube step
  to enable once a SonarQube server/project key exists.

## AI-assisted engineering

See `docs/ai-assisted-workflow.md` for how Generative AI was used on this project
(structured prompts, generated scaffolding, human review) — the JD asks for practical
experience with AI-assisted coding tools, and this project documents that workflow
instead of only claiming it.

## Layout

```
src/main/java/com/dharma/banking/
  BankingApiApplication.java        # Spring Boot entry point
  model/       Account, Transaction, TransactionType
  dto/         CreateAccountRequest, MoneyRequest, TransferRequest,
               AccountResponse, TransactionResponse, ErrorResponse
  repository/  AccountRepository (interface) + InMemoryAccountRepository
  service/     AccountService + AccountNotFoundException + InsufficientFundsException
  controller/  AccountController
  exception/   GlobalExceptionHandler (one error shape for every failure)
  gateway/     RequestContextFilter, RateLimitFilter, RateLimiter, RequestMetrics,
               GatewayConfig (request ids, rate limiting, per-route metrics)
  ops/         OpsController (GET /ops/health, GET /ops/metrics)
src/test/java/com/dharma/banking/
  AccountServiceTest.java  AccountControllerTest.java
  gateway/RateLimiterTest.java  gateway/GatewayFiltersTest.java
```
