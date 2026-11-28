"""Amazon Bedrock model gateway: model registry, routing, guardrails and
prompt management.

The gateway is the single front door for every model call on the platform:
teams call the gateway, never Bedrock directly. It picks a healthy model
with capacity headroom, applies guardrails (PII redaction, blocked topics)
before the call, and records the prompt template version used so any
answer can be reproduced and audited.

No real Bedrock or network calls are made here. ``invoke`` runs against a
deterministic stand-in generator so the gateway, routing, guardrails and
metering can be tested offline; a real Bedrock client plugs into the same
``ModelBackend.invoke`` interface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Cost per 1,000 tokens, in USD — the figures the platform publishes for
# chargeback. They are planning figures for the demo, not a live price list.
MODEL_CATALOG = {
    "anthropic.claude-3-5-sonnet-20241022-v2:0": {
        "provider": "Anthropic",
        "max_tokens": 8192,
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
        "latency_ms_p50": 900,
    },
    "amazon.titan-text-premier-v1:0": {
        "provider": "Amazon",
        "max_tokens": 4096,
        "cost_per_1k_input": 0.0005,
        "cost_per_1k_output": 0.0015,
        "latency_ms_p50": 400,
    },
    "meta.llama3-70b-instruct-v1:0": {
        "provider": "Meta",
        "max_tokens": 4096,
        "cost_per_1k_input": 0.00065,
        "cost_per_1k_output": 0.0008,
        "latency_ms_p50": 700,
    },
    "cohere.command-r-plus-v1:0": {
        "provider": "Cohere",
        "max_tokens": 4096,
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
        "latency_ms_p50": 800,
    },
}

BLOCKED_TOPICS = ("weapons", "how to evade sanctions", "insider trading tips")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
ACCOUNT_RE = re.compile(r"\b\d{10,12}\b")


@dataclass
class ModelBackend:
    """One model behind the gateway, with health and capacity state."""

    model_id: str
    healthy: bool = True
    capacity_headroom: float = 1.0  # 0..1, fraction of capacity still free
    calls: int = 0

    def invoke(self, prompt: str) -> str:
        """Deterministic stand-in for a Bedrock InvokeModel call.

        A real Bedrock client replaces this method; the gateway never
        depends on what the generator returns, only on its interface.
        """
        self.calls += 1
        return f"[{self.model_id}] answer to: {prompt[:120]}"


@dataclass
class PromptTemplate:
    """A versioned prompt template teams reuse instead of free text."""

    name: str
    version: int
    template: str

    def render(self, **values: str) -> str:
        try:
            return self.template.format(**values)
        except KeyError as exc:
            raise ValueError(f"missing prompt variable: {exc}") from exc


@dataclass
class Gateway:
    """The model gateway: registry, routing, guardrails, metering."""

    backends: list[ModelBackend] = field(default_factory=list)
    templates: dict[str, PromptTemplate] = field(default_factory=dict)
    usage: list[dict] = field(default_factory=list)

    def register(self, backend: ModelBackend) -> None:
        if backend.model_id not in MODEL_CATALOG:
            raise ValueError(f"unknown model: {backend.model_id}")
        self.backends.append(backend)

    def route(self, preferred: str | None = None) -> ModelBackend:
        """Pick the preferred model when healthy, else the healthy model
        with the most capacity headroom. Fail over, never fail open."""
        healthy = [b for b in self.backends if b.healthy]
        if not healthy:
            raise RuntimeError("no healthy model backend available")
        if preferred:
            for backend in healthy:
                if backend.model_id == preferred:
                    return backend
        return max(healthy, key=lambda b: b.capacity_headroom)

    @staticmethod
    def apply_guardrails(prompt: str) -> tuple[str, list[str]]:
        """Redact PII and block disallowed topics. Returns the cleaned
        prompt and a list of guardrail actions taken."""
        actions: list[str] = []
        lowered = prompt.lower()
        for topic in BLOCKED_TOPICS:
            if topic in lowered:
                raise ValueError(f"blocked topic in prompt: {topic}")
        cleaned = prompt
        if SSN_RE.search(cleaned):
            cleaned = SSN_RE.sub("[SSN REDACTED]", cleaned)
            actions.append("redacted SSN")
        if ACCOUNT_RE.search(cleaned):
            cleaned = ACCOUNT_RE.sub("[ACCOUNT REDACTED]", cleaned)
            actions.append("redacted account number")
        return cleaned, actions

    def invoke(
        self,
        prompt: str,
        *,
        team: str,
        use_case: str,
        preferred_model: str | None = None,
        template: str | None = None,
        **template_values: str,
    ) -> dict:
        """Guardrail, route, invoke, meter. Returns the answer plus the
        metering record the observability layer consumes."""
        if template:
            if template not in self.templates:
                raise ValueError(f"unknown prompt template: {template}")
            prompt = self.templates[template].render(**template_values)
        cleaned, guardrail_actions = self.apply_guardrails(prompt)
        backend = self.route(preferred_model)
        answer = backend.invoke(cleaned)
        input_tokens = max(1, len(cleaned.split()))
        output_tokens = max(1, len(answer.split()))
        spec = MODEL_CATALOG[backend.model_id]
        cost = (
            input_tokens / 1000 * spec["cost_per_1k_input"]
            + output_tokens / 1000 * spec["cost_per_1k_output"]
        )
        record = {
            "team": team,
            "use_case": use_case,
            "model_id": backend.model_id,
            "template": template,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 6),
            "latency_ms_p50": spec["latency_ms_p50"],
            "guardrail_actions": guardrail_actions,
        }
        self.usage.append(record)
        return {"answer": answer, "record": record}

    def cost_by_team(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for record in self.usage:
            totals[record["team"]] = round(
                totals.get(record["team"], 0.0) + record["cost_usd"], 6
            )
        return totals
