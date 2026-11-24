# Deployment Playbook: Support knowledge assistant

Domain: IT support
Use case: Answer employee questions from policy documents with citations, escalating anything ungrounded.

## Evaluation evidence

- Eval cases run: 5
- Passed: 5 (pass rate 100%)
- Mean correctness: 0.90
- Mean grounding: 1.00
- p95 latency: 0.17 ms
- Total cost: $0.0007
- PII leaks: 0

## Readiness verdict

**READY FOR PRODUCTION**

- [PASS] eval pass rate: 1.00 vs minimum 0.8
- [PASS] mean grounding: 1.00 vs minimum 0.9
- [PASS] p95 latency: 0.17 ms vs maximum 2000.0 ms
- [PASS] cost per case: $0.0001 vs maximum $0.05
- [PASS] PII leaks: 0 leaks vs maximum 0

## Rollout steps

1. Pilot with one customer team and a human in the loop on every escalated question.
2. Watch the JSONL eval log daily: pass rate, grounding, latency, cost and PII leaks.
3. Expand to more teams only after two consecutive passing eval runs with no PII leaks.
4. Re-run the eval suite on every prompt, tool or document change; a failing gate blocks the release.

## Risks and open items

- The agent answers only from retrieved documents; questions with no grounding document escalate to a human.
- Graders are deterministic rule-based stubs: swap in model-backed graders and human review before high-stakes decisions.
- Cost figures are estimates from a token heuristic, not a bill.

## Use-case ranking (this deployment)

- Support knowledge assistant: score 6.15 (pilot)
- Contract clause summariser: score 2.95 (defer)
