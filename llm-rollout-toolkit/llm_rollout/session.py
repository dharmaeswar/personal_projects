"""Session management with context compaction.

A Session holds the message history for one rollout. When the token
budget is exceeded, `compact` keeps the system prompt and the most
recent turns and replaces the dropped middle with a short summary
record, so the rollout can continue inside the budget.
"""
from . import tokenizer


class Session:
    def __init__(self, system_prompt: str = "", token_budget: int = 4096):
        self.token_budget = token_budget
        self.messages: list[dict] = []
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})

    def add(self, role: str, content: str, **extra):
        msg = {"role": role, "content": content}
        msg.update(extra)
        self.messages.append(msg)

    def token_count(self) -> int:
        return sum(tokenizer.count(m["content"]) for m in self.messages)

    def over_budget(self) -> bool:
        return self.token_count() > self.token_budget

    def compact(self) -> dict:
        """Drop oldest non-system turns until inside budget, replacing
        them with a short summary record. Returns a report of what was
        dropped. If even the system prompt plus summary exceeds the
        budget, the oldest turns are all dropped and the summary stays."""
        if not self.over_budget():
            return {"dropped": 0, "summary": None}
        system = [m for m in self.messages if m["role"] == "system"]
        rest = [m for m in self.messages if m["role"] != "system"]
        dropped = 0
        while True:
            summary = f"[{dropped} turns compacted]" if dropped else None
            candidate = list(system)
            if summary:
                candidate.append({"role": "system", "content": summary})
            candidate.extend(rest)
            total = sum(tokenizer.count(m["content"]) for m in candidate)
            if total <= self.token_budget or not rest:
                self.messages = candidate
                return {"dropped": dropped, "summary": summary}
            rest.pop(0)
            dropped += 1
