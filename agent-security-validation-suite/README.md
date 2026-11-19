# Agent Security Validation Suite

An adversarial test harness for AI agents, built for an Applied
Scientist (AGI/AI Security) role: it measures whether an agent's
guardrails, MCP tool authorization, and behavior monitoring actually
hold up against prompt injection, jailbreak, PII exfiltration, tool
abuse, and data-exfiltration attempts.

All cases are synthetic and deterministic. No real LLM or API calls:
the agents are fixed policies and the attacks are fixed text, so every
eval is reproducible with no model cost.

## What it does

- **Guardrails** (`agent_security/guardrails.py`): pattern-based
  detectors for prompt injection, PII, destructive tool use, and
  exfiltration, combined into a block/allow decision with a risk score.
- **Attack cases** (`agent_security/attacks.py`): 16 attack cases across
  5 categories (prompt injection, jailbreak, PII exfiltration, tool
  abuse, data exfiltration) plus 8 benign controls that must stay allowed.
- **MCP authorization** (`agent_security/mcp.py`): a 10-tool registry
  with per-tool scopes. Sensitive tools are denied without the scope,
  and their arguments are guardrail-scanned even when the scope is held,
  so an injection payload smuggled into a tool call is denied.
- **Session monitor** (`agent_security/monitor.py`): watches the tool-call
  stream and flags call bursts, repeated denials, retries of a denied
  sensitive tool, and read-then-export sequences.
- **Eval runner** (`agent_security/evals.py`): scores the suites and
  reports bypass rate, false-positive rate, and per-category results.

## Run

```bash
pip install -r requirements.txt   # pytest only; everything else is stdlib
python run_validation.py
python -m pytest -q
```

## Results (seeded, reproducible)

- Guardrail evals: **24/24 passed** — bypass rate **0.0%** (no attack got
  through), false-positive rate **0.0%** (no benign case blocked).
- Per category: prompt injection 6/6, jailbreak 2/2, PII exfiltration 3/3,
  tool abuse 3/3, data exfiltration 2/2, benign 8/8.
- MCP authorization scenarios: **12/12 passed** — unknown tools denied,
  missing scopes denied, injection in tool args denied, authorized calls allowed.
- Session monitor demo session: **3 anomalies flagged** — a 6-call burst
  in 60s, 3 consecutive denials, and a sensitive tool succeeding after denial.
- Tests: **18 pytest tests, all passing**.

## Notes and limits

- **All data is synthetic.** Prompts, SSNs, card numbers, and tool calls
  are invented for this harness; the SSN and card number are fake.
- Detectors are fixed regex rules, not a learned model: they show the
  eval-harness shape (cases, scoring, authorization boundaries, monitoring),
  not production detection science.
- The harness runs locally in plain Python (standard library + pytest).
