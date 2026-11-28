"""Session management with context compaction.

A session holds the message history for one conversation and counts its
tokens with the tokenizer. When the history grows past a token budget,
``compact`` drops the oldest non-system turns first — the system prompt
and the most recent turns are the last things to go — and reports how many
messages were dropped, so the caller can see exactly what was lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .rendering import Message
from .tokenizer import SimpleTokenizer


@dataclass
class Session:
    """One conversation: its messages, tokenizer, and compaction budget."""

    messages: list[Message] = field(default_factory=list)
    tokenizer: SimpleTokenizer = field(default_factory=SimpleTokenizer)

    def append(self, message: Message) -> None:
        self.messages.append(message)

    def token_count(self) -> int:
        """Tokens in the whole history, counting each message's content."""
        total = 0
        for message in self.messages:
            total += len(self.tokenizer.encode(message.content))
        return total

    def compact(self, max_tokens: int) -> int:
        """Drop oldest non-system turns until within ``max_tokens``.

        Returns the number of messages dropped. The system message (if
        any) is never dropped; if even the system message alone exceeds
        the budget, compaction stops and reports what it dropped.
        """
        dropped = 0
        while self.token_count() > max_tokens and len(self.messages) > 1:
            # Drop the oldest message that is not the system prompt.
            idx = next((i for i, m in enumerate(self.messages) if m.role != "system"), None)
            if idx is None:
                break
            del self.messages[idx]
            dropped += 1
        return dropped
