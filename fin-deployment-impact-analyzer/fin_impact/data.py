"""Synthetic support-conversation data for Fin deployment measurement.

One row per support conversation: which customer, which channel, whether
it happened before or after the Fin deployment, whether Fin resolved it
end to end, handle time, CSAT, and whether it escalated to a human.
All data is synthetic and seeded; no real customers, conversations,
or Intercom/Fin data is used.
"""

import random

CHANNELS = ("chat", "email", "voice")
CUSTOMERS = ("acme", "globex", "initech", "umbrella", "hooli")


class Conversation:
    """One synthetic support conversation."""

    def __init__(self, conv_id, customer, channel, period, resolved_by_fin,
                 handle_minutes, csat, escalated):
        self.conv_id = conv_id
        self.customer = customer
        self.channel = channel
        self.period = period  # "before" or "after" the Fin deployment
        self.resolved_by_fin = resolved_by_fin
        self.handle_minutes = handle_minutes
        self.csat = csat  # 1-5, or None when no survey answered
        self.escalated = escalated

    def as_row(self):
        return (self.conv_id, self.customer, self.channel, self.period,
                int(self.resolved_by_fin), self.handle_minutes,
                self.csat, int(self.escalated))


def make_conversations(n_per_customer=400, seed=42):
    """Seeded conversations across 5 customers, before and after Fin.

    After deployment Fin resolves a real share of conversations, handle
    time falls, and escalations drop — with per-customer variation so
    the comparison has realistic (not inflated) power.
    """
    rng = random.Random(seed)
    convs = []
    cid = 0
    for customer in CUSTOMERS:
        fin_rate = rng.uniform(0.42, 0.58)
        for _ in range(n_per_customer):
            cid += 1
            channel = rng.choice(CHANNELS)
            period = "after" if rng.random() < 0.5 else "before"
            if period == "after":
                resolved = rng.random() < fin_rate
                handle = round(rng.gauss(6.0 if resolved else 14.0, 3.0), 1)
                escalated = (not resolved) and rng.random() < 0.18
                csat = rng.choice([5, 5, 4, 4, 4, 3]) if rng.random() < 0.7 else None
            else:
                resolved = False
                handle = round(rng.gauss(16.0, 4.0), 1)
                escalated = rng.random() < 0.30
                csat = rng.choice([5, 4, 4, 3, 3, 2]) if rng.random() < 0.6 else None
            convs.append(Conversation(
                f"C{cid:05d}", customer, channel, period, resolved,
                max(0.5, handle), csat, escalated))
    return convs
