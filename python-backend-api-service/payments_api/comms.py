"""Communications platform module for the backend service.

Transactional messaging for the loan product: a message is rendered from a
template, fanned out to the channels the user has enabled, and delivered
through a provider abstraction with safe retries and confirmed delivery.

What it covers (mirrors a real comms platform, stdlib only):

- Templates: named templates per channel with ``{{placeholder}}`` variables.
  Rendering fails loudly on a missing variable instead of sending a broken
  message.
- Delivery providers: a ``DeliveryProvider`` interface; the
  ``SimulatedProvider`` below stands in for real providers (email / SMS /
  push / Slack / Teams / WhatsApp) and can be told to fail transiently so
  the retry path is exercised. No real provider is called.
- User preferences: per-user enabled channels and a digest opt-in. A send
  only goes to channels the user has enabled.
- Idempotent delivery: a retried send with the same idempotency key returns
  the original message record and never delivers twice.
- Safe retries: each channel delivery is retried with exponential backoff
  (bounded attempts) and only marked delivered when the provider confirms
  it. A delivery that exhausts retries is recorded as failed, never lost
  silently.
- Delivery monitoring: a per-channel delivery log and a summary with
  counts and delivery rate.
- Digesting: several messages for one user can be grouped into a single
  digest per channel instead of one notification each.
"""

from __future__ import annotations

import itertools
import re
import threading

from .idempotency import IdempotencyStore, retry_with_backoff

CHANNELS = ("email", "sms", "push", "slack", "teams", "whatsapp")

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class TemplateError(ValueError):
    """Raised when a template cannot be rendered (unknown template / missing var)."""


class MessageTemplate:
    """A named message template for one channel."""

    def __init__(self, name: str, channel: str, subject: str, body: str) -> None:
        if channel not in CHANNELS:
            raise TemplateError(f"unknown channel: {channel!r}")
        if not name:
            raise TemplateError("template name must not be empty")
        self.name = name
        self.channel = channel
        self.subject = subject
        self.body = body

    def render(self, variables: dict) -> dict:
        """Render subject and body. Raises TemplateError on a missing variable."""

        def _fill(text: str) -> str:
            missing = sorted(set(_PLACEHOLDER_RE.findall(text)) - set(variables))
            if missing:
                raise TemplateError(
                    f"template {self.name!r} missing variables: {', '.join(missing)}"
                )
            return _PLACEHOLDER_RE.sub(lambda m: str(variables[m.group(1)]), text)

        return {"subject": _fill(self.subject), "body": _fill(self.body)}


# Built-in templates for the loan product (transactional messages).
TEMPLATES = {
    "payment_due": MessageTemplate(
        "payment_due",
        "email",
        "Payment due: {{amount}} on loan {{loan_id}}",
        "Hi {{customer_id}}, your next installment of {{amount}} for loan "
        "{{loan_id}} is due on {{due_date}}. Thank you.",
    ),
    "payment_received": MessageTemplate(
        "payment_received",
        "sms",
        "",
        "Payment of {{amount}} received for loan {{loan_id}}. "
        "Remaining balance: {{remaining}}.",
    ),
    "loan_approved": MessageTemplate(
        "loan_approved",
        "push",
        "",
        "Your loan {{loan_id}} for {{amount}} was approved. "
        "First installment due {{due_date}}.",
    ),
}


class DeliveryProvider:
    """Interface for a channel delivery provider.

    ``send`` must return a provider message id on confirmed delivery and
    raise RuntimeError on a transient failure (so the caller can retry).
    """

    def send(self, channel: str, recipient: str, subject: str, body: str) -> str:
        raise NotImplementedError


class SimulatedProvider(DeliveryProvider):
    """Stand-in for real providers (Twilio / SendGrid / Slack / etc.).

    Records every delivery in memory and can be told to fail the first
    ``fail_times`` sends with a transient error, so the retry path is
    exercised. Nothing here calls a real provider.
    """

    def __init__(self, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.calls = 0
        self.delivered: list[dict] = []
        self._lock = threading.Lock()

    def send(self, channel: str, recipient: str, subject: str, body: str) -> str:
        with self._lock:
            self.calls += 1
            if self.calls <= self.fail_times:
                raise RuntimeError("provider temporarily unavailable")
            message_id = f"{channel}_msg_{len(self.delivered) + 1:06d}"
            self.delivered.append(
                {
                    "provider_message_id": message_id,
                    "channel": channel,
                    "recipient": recipient,
                    "subject": subject,
                    "body": body,
                }
            )
            return message_id


class UserPreferences:
    """Per-user channel preferences and digest opt-in.

    Default: every channel enabled, digest off. Preferences are stored
    in memory; a send only targets channels the user has enabled.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._channels: dict[str, list[str]] = {}
        self._digest: dict[str, bool] = {}

    def set_channels(self, user_id: str, channels: list[str]) -> list[str]:
        unknown = [c for c in channels if c not in CHANNELS]
        if unknown:
            raise TemplateError(f"unknown channels: {', '.join(unknown)}")
        if not channels:
            raise TemplateError("at least one channel must stay enabled")
        with self._lock:
            self._channels[user_id] = list(dict.fromkeys(channels))
            return list(self._channels[user_id])

    def channels_for(self, user_id: str) -> list[str]:
        with self._lock:
            return list(self._channels.get(user_id, CHANNELS))

    def set_digest(self, user_id: str, enabled: bool) -> bool:
        with self._lock:
            self._digest[user_id] = bool(enabled)
            return self._digest[user_id]

    def digest_enabled(self, user_id: str) -> bool:
        with self._lock:
            return self._digest.get(user_id, False)


def build_digest(user_id: str, channel: str, messages: list[dict]) -> dict:
    """Group several rendered messages into one digest for a user/channel.

    Returns a single digest message; an empty input raises TemplateError.
    """
    if not messages:
        raise TemplateError("cannot build a digest with no messages")
    lines = [f"- {m['subject'] or m['body']}" for m in messages]
    if any(m["subject"] for m in messages):
        lines = [
            f"- {m['subject']}: {m['body']}" if m["subject"] else f"- {m['body']}"
            for m in messages
        ]
    return {
        "user_id": user_id,
        "channel": channel,
        "subject": f"Your digest: {len(messages)} updates",
        "body": "\n".join(lines),
        "message_count": len(messages),
    }


class CommsService:
    """Owns template rendering, preference filtering, delivery and logging."""

    def __init__(
        self,
        provider: DeliveryProvider,
        idempotency: IdempotencyStore | None = None,
        preferences: UserPreferences | None = None,
    ) -> None:
        self.provider = provider
        self.idempotency = idempotency or IdempotencyStore()
        self.preferences = preferences or UserPreferences()
        self._lock = threading.Lock()
        self._counter = itertools.count(1)
        self._messages: dict[str, dict] = {}
        self._log: list[dict] = []

    def send(
        self,
        template_name: str,
        user_id: str,
        recipient: str,
        variables: dict,
        channels: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """Render a template and deliver it to the user's enabled channels.

        A retried send with the same idempotency key returns the original
        record without delivering again. Each channel is retried with
        exponential backoff and only marked delivered on provider
        confirmation.
        """
        if idempotency_key:
            cached = self.idempotency.get(idempotency_key)
            if cached is not None:
                return cached
        template = TEMPLATES.get(template_name)
        if template is None:
            raise TemplateError(f"unknown template: {template_name!r}")
        rendered = template.render(variables)
        requested = channels if channels is not None else [template.channel]
        unknown = [c for c in requested if c not in CHANNELS]
        if unknown:
            raise TemplateError(f"unknown channels: {', '.join(unknown)}")
        enabled = self.preferences.channels_for(user_id)
        targets = [c for c in requested if c in enabled]
        if not targets:
            raise TemplateError(
                f"user {user_id!r} has none of the requested channels enabled"
            )
        with self._lock:
            message_id = f"msg_{next(self._counter):06d}"
        deliveries = []
        for channel in targets:
            try:
                provider_id = retry_with_backoff(
                    lambda c=channel: self.provider.send(
                        c, recipient, rendered["subject"], rendered["body"]
                    )
                )
                status = "delivered"
            except RuntimeError:
                provider_id = None
                status = "failed"
            entry = {
                "channel": channel,
                "status": status,
                "provider_message_id": provider_id,
            }
            deliveries.append(entry)
            with self._lock:
                self._log.append({"message_id": message_id, **entry})
        overall = (
            "delivered"
            if all(d["status"] == "delivered" for d in deliveries)
            else "partial"
            if any(d["status"] == "delivered" for d in deliveries)
            else "failed"
        )
        record = {
            "id": message_id,
            "template": template_name,
            "user_id": user_id,
            "channels": targets,
            "subject": rendered["subject"],
            "body": rendered["body"],
            "status": overall,
            "deliveries": deliveries,
        }
        with self._lock:
            self._messages[message_id] = record
        if idempotency_key:
            self.idempotency.put(idempotency_key, record)
        return record

    def get(self, message_id: str) -> dict | None:
        with self._lock:
            record = self._messages.get(message_id)
            return dict(record) if record is not None else None

    def delivery_summary(self) -> dict:
        """Delivery monitoring: counts and rate per channel and overall."""
        with self._lock:
            log = list(self._log)
        per_channel: dict[str, dict] = {}
        for entry in log:
            bucket = per_channel.setdefault(
                entry["channel"], {"attempted": 0, "delivered": 0, "failed": 0}
            )
            bucket["attempted"] += 1
            bucket[entry["status"]] += 1
        total = len(log)
        delivered = sum(1 for e in log if e["status"] == "delivered")
        return {
            "total_attempts": total,
            "delivered": delivered,
            "failed": total - delivered,
            "delivery_rate": (delivered / total) if total else 1.0,
            "per_channel": per_channel,
        }
