# Agentic Commerce Checkout Service

A deterministic backend service for agentic commerce: AI agents invoke
secure checkout and payment APIs on a user's behalf, and every step is
checked before any money moves. Built as the role project for the
**Global Payments — Senior Software Engineer, Agentic Commerce**
(R0077212, Atlanta GA) role.

The problem it answers: when an AI agent discovers a product, builds a
cart, and initiates a purchase for a consumer, the payments layer needs
new infrastructure for trust, identity, user intent, authentication,
tokenization, fraud signals, and real-time transaction visibility. This
service is a working model of that layer — verifiable intent, delegated
credentials, tokenized payment data, risk signals, idempotent capture,
MCP-style tool calls, and a hash-chained audit trail.

All data is synthetic. No network calls, no model calls, no real
payments, no real card numbers. Standard library only, plus pytest.

## What it does

- **Verifiable intent** (`agentic_checkout/intent.py`): an agent's request
  (agent, user, merchant, action, amount, currency, idempotency key) is
  checked field-by-field against the user's delegation — action allowed,
  merchant allowlisted, amount within the cap, currency allowed, not
  expired. A violation stops the flow with a plain-language reason.
- **Delegated credentials** (`agentic_checkout/tokens.py`): HMAC-SHA256
  signed agentic tokens carrying scopes, merchant allowlist, spend cap,
  and expiry. Tampering breaks the signature. A replay guard refuses a
  token/idempotency-key pair it has already seen.
- **Tokenization** (`agentic_checkout/vault.py`): card numbers become
  opaque `tok_...` references; only brand and last four digits are ever
  returned. Luhn-checked; synthetic test numbers only.
- **Fraud / risk signals** (`agentic_checkout/risk.py`): deterministic
  scoring from amount anomaly vs the merchant's median ticket, velocity
  (attempts per agent in a window), first payment to a new merchant, and
  a blocked-merchant list. Scores 0-100 map to ALLOW / REVIEW / DENY,
  with every contributing reason listed.
- **Checkout service** (`agentic_checkout/checkout.py`): create checkout,
  authorize, capture, refund. Capture is idempotent — repeating it with
  the same key returns the original receipt instead of charging twice.
  Refunds are capped at the captured balance.
- **MCP-style tools** (`agentic_checkout/mcp_tools.py`): JSON schemas for
  `create_checkout`, `authorize_payment`, `capture_payment`,
  `refund_payment`, `get_transaction_status`. Arguments are validated
  against the schema before any service call runs.
- **Audit trail** (`agentic_checkout/audit.py`): hash-chained, append-only
  log of intent fingerprint, token id, risk decision, and outcome — the
  transaction evidence needed for disputes and reporting. Tampering is
  detected by `verify_chain()`.

## How to run

```bash
pip install -r requirements.txt
python -m pytest -q        # 31 tests
python run_demo.py         # one agent purchase end to end
```

## Honest limits

- Demo scale: in-memory state, one process, no persistence, no
  distributed systems. It demonstrates the checkout, intent, token,
  risk, and audit semantics — not a scaled-out service.
- The signing secret in `api.py` is labelled DEMO; a real deployment
  holds it in a vault/KMS and never ships it in code.
- Risk scoring is rule-based (amount anomaly, velocity, new merchant),
  not a machine-learned fraud model.
- The agents are deterministic stand-ins: the service validates and
  executes tool calls, but no LLM plans or places orders here.
- UCP / ACP / AP2 are modelled as delegated-authority concepts (signed
  tokens, verifiable intent, scoped tools), not as protocol clients —
  no live integration with any of those protocols is claimed.
