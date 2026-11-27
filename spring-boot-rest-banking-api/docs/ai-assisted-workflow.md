# AI-assisted engineering workflow

The JD asks for practical experience using Generative AI, prompt engineering, and
AI-assisted coding tools within software-development workflows. This note records
how that was done on this project — the workflow itself, not a claim that AI wrote
unchecked code.

## How AI was used

1. **Scaffolding prompt (structured):** "Generate a Spring Boot 3 REST service in
   Java 17 with layered packages (controller / service / repository / model / dto),
   BigDecimal money handling, JUnit 5 + MockMvc tests, and a GitHub Actions CI
   workflow. No Lombok, no database — in-memory storage behind an interface."
2. **Test-generation prompt:** "For each service rule (overdraft rejection, idempotent
   transfer replay, concurrent deposits, validation failures), write a failing-first
   JUnit test that pins the exact behaviour, including the balance after the failure."
3. **Review prompt:** "Review this service for secure-coding issues: double money,
   missing validation, leaked sensitive data in logs, deadlock risk on transfers."

## Human gates (what AI did not decide)

- Every generated file was read and edited by hand before it was kept; the transfer
  lock-ordering and the idempotency replay were designed first, then generated.
- The test suite was run locally (`mvn test`) until green — 18 tests, 0 failures —
  before the project was pushed. A green run, not the generation step, is the
  quality evidence.
- No generated code was trusted on its face: the concurrency test exists precisely
  because a race in deposit handling would not show up in a code review.

## What this demonstrates

- Structured prompting: each prompt names the stack, the layering, the exact rules
  to pin down, and what is out of scope.
- AI-assisted coding inside a normal engineering loop: generate, review, test, fix —
  with tests as the check that the assisted code actually behaves.
