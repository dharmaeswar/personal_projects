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
- **ABAC / attribute repository** (`agent_security/abac.py`): a CARDS-style
  consolidated attribute store for principals and resources, plus a
  deny-by-default policy engine for identity and access decisions. Rules
  cover same-team and cross-team reads, MFA-gated writes, contractor and
  service-account limits on restricted resources, stale-attribute deny
  until refresh, a clearance-must-meet-classification invariant, and
  field-level (FGAC) denial of sensitive fields without same-team + MFA.
- **Autonomous detection/response** (`agent_security/autonomous.py`):
  AI/ML-style security automation — detectors over normalized threat
  signals (brute-force bursts, egress anomalies, privilege-escalation
  chains, known-bad indicator matches) produce findings with severity
  and confidence, and a responder executes low-risk containment
  automatically (revoke session, quarantine host, block indicator) while
  holding destructive actions (disable account, isolate network) for
  human approval. Responses are idempotent per finding id.
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
- ABAC / CARDS scenarios: **13/13 passed** — 4 allowed, 9 denied. Denials
  cover cross-team confidential reads, low-clearance reads, writes without
  MFA, restricted resources for contractors/service accounts, stale
  attributes, and unknown principals/resources. Field-level control: a
  sensitive field is denied without same-team + MFA even when the read
  itself is allowed.
- Autonomous detection/response scenarios: **8/8 passed** — brute-force
  bursts and egress spikes detected with sessions revoked, privilege
  escalation held for human approval, known-bad indicators quarantined,
  and below-threshold signals left alone.
- Tests: **41 pytest tests, all passing** (18 guardrail/MCP/monitor + 13 ABAC + 10 autonomous).

## Notes and limits

- **All data is synthetic.** Prompts, SSNs, card numbers, and tool calls
  are invented for this harness; the SSN and card number are fake.
- Detectors are fixed regex rules, not a learned model: they show the
  eval-harness shape (cases, scoring, authorization boundaries, monitoring),
  not production detection science.
- The harness runs locally in plain Python (standard library + pytest).
