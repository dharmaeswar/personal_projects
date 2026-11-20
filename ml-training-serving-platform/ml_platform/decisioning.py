"""Next-best-action decisioning: model score + business rules.

Given the production model from the registry and a member profile, this
module scores a small set of candidate next-best-actions, applies simple
eligibility and business rules (suppress an action the member already
completed, cap contacts per member per week), and picks the best eligible
action.

This is model-score + business-rule decisioning only. It is NOT
reinforcement learning, bandit optimisation, or any other adaptive
policy: scores come from the registered model plus fixed per-action
affinity rules, and the rules are applied deterministically. All member
data is synthetic and generated with a seeded RNG.
"""

import json
import os
import random
from datetime import datetime, timezone

from .training import LogisticModel

# Candidate next-best-actions. "priority" is the tie-break order for the
# rule-only baseline: lower numbers are tried first.
ACTIONS = [
    {"id": "care_gap_reminder", "label": "Care-gap reminder",
     "channel": "sms", "priority": 1},
    {"id": "preventive_screening_nudge", "label": "Preventive screening nudge",
     "channel": "email", "priority": 2},
    {"id": "wellness_program_invite", "label": "Wellness program invite",
     "channel": "email", "priority": 3},
    {"id": "benefits_explanation", "label": "Benefits explanation",
     "channel": "phone", "priority": 4},
]

DEFAULT_MAX_CONTACTS_PER_WEEK = 2
# A screening is "up to date" if one happened within this many days.
SCREENING_FRESH_DAYS = 180


def generate_members(n, seed=42):
    """Return n synthetic member profiles.

    Each profile carries the numeric feature vector the registered model
    expects plus the fields the eligibility rules read. Nothing here is
    real member data.
    """
    rng = random.Random(seed)
    members = []
    for i in range(n):
        members.append({
            "member_id": f"member-{i + 1:04d}",
            "features": {
                "income": round(rng.uniform(25_000, 180_000), 2),
                "debt_ratio": round(rng.uniform(0.05, 0.85), 4),
                "credit_history_years": round(rng.uniform(0.5, 25.0), 2),
                "delinquencies": rng.choice([0, 0, 0, 1, 1, 2, 3]),
                "amount": round(rng.uniform(500, 25_000), 2),
            },
            "has_care_gap": rng.random() < 0.4,
            "completed_actions": sorted(rng.sample(
                [a["id"] for a in ACTIONS],
                k=rng.choice([0, 0, 1]))),
            "wellness_enrolled": rng.random() < 0.3,
            "last_screening_days_ago": rng.randint(30, 400),
            "contacts_this_week": rng.choice([0, 0, 1, 1, 2, 3]),
        })
    return members


def _sigmoid(x):
    import math

    return 1.0 / (1.0 + math.exp(-x)) if x >= -700 else 0.0


# Fixed per-action sensitivities to the model's standardised features.
# These are hand-written scoring rules, NOT learned weights: they say
# which member characteristics make an action more relevant (e.g. a
# benefits explanation matters more when the requested amount is high).
# Because they use the model's own standardised features, the model's
# weights and the member's profile both shape the ranking — the model
# genuinely changes which action is picked, unlike a shared propensity
# alone, which would be identical for every candidate.
_ACTION_SENSITIVITY = {
    "care_gap_reminder": {"debt_ratio": 0.5, "delinquencies": 0.4,
                          "credit_history_years": -0.2},
    "preventive_screening_nudge": {"credit_history_years": 0.4, "income": 0.2},
    "wellness_program_invite": {"income": -0.3, "debt_ratio": -0.3},
    "benefits_explanation": {"amount": 0.6, "income": -0.2},
}


def _affinity(action_id, member, model=None):
    """Per-action affinity in (0, 1) from the member profile.

    Combines a fixed base relevance (e.g. a care-gap reminder matters
    most when the member actually has an open care gap) with the
    action's fixed sensitivities to the member's standardised features.
    Hand-written rule, not a learned value.
    """
    if action_id == "care_gap_reminder":
        base = 1.2 if member["has_care_gap"] else -1.0
    elif action_id == "preventive_screening_nudge":
        base = 0.8 if member["last_screening_days_ago"] > SCREENING_FRESH_DAYS else -1.0
    elif action_id == "wellness_program_invite":
        base = 0.6 if not member["wellness_enrolled"] else -1.0
    elif action_id == "benefits_explanation":
        base = 0.0
    else:
        base = 0.0
    if model is not None:
        z = {f: (member["features"][f] - m) / s
             for f, m, s in zip(model.features, model.means, model.stds)}
        base += sum(coef * z[f] for f, coef in _ACTION_SENSITIVITY.get(action_id, {}).items())
    return _sigmoid(base)


def _rules_for(action_id, member, max_contacts_per_week):
    """Return the list of rules that suppress this action for this member."""
    rules = []
    if action_id in member["completed_actions"]:
        rules.append("already_completed")
    if action_id == "care_gap_reminder" and not member["has_care_gap"]:
        rules.append("no_open_care_gap")
    if (action_id == "preventive_screening_nudge"
            and member["last_screening_days_ago"] <= SCREENING_FRESH_DAYS):
        rules.append("screening_up_to_date")
    if action_id == "wellness_program_invite" and member["wellness_enrolled"]:
        rules.append("already_enrolled")
    if member["contacts_this_week"] >= max_contacts_per_week:
        rules.append("weekly_contact_cap")
    return rules


def baseline_action(member, candidates=None, max_contacts_per_week=DEFAULT_MAX_CONTACTS_PER_WEEK):
    """Rule-only baseline: first eligible action in priority order.

    Ignores model scores entirely, so outcome comparisons can show what
    the model adds over fixed priority ordering.
    """
    candidates = candidates or ACTIONS
    ordered = sorted(candidates, key=lambda a: a["priority"])
    for action in ordered:
        if not _rules_for(action["id"], member, max_contacts_per_week):
            return action["id"]
    return None


class DecisioningEngine:
    """Score candidate actions with the production model + rules."""

    def __init__(self, registry, max_contacts_per_week=DEFAULT_MAX_CONTACTS_PER_WEEK):
        self.registry = registry
        self.max_contacts_per_week = max_contacts_per_week

    def _production_model(self):
        version = self.registry.production_version()
        if version is None:
            raise ValueError("no production model registered")
        entry = self.registry.get(version)
        return version, LogisticModel.from_dict(entry["model"])

    def decide(self, member, candidates=None, timestamp=None):
        """Pick the best eligible next-best-action for one member.

        Returns a decision dict with the chosen action, the production
        model version, per-action scores, and the rule outcome for every
        candidate. `timestamp` is injectable so tests stay deterministic.
        """
        version, model = self._production_model()
        candidates = candidates or ACTIONS
        propensity = model.predict_proba(member["features"])
        scores = {}
        rules_applied = {}
        for action in candidates:
            action_id = action["id"]
            # Model propensity blended with the per-action affinity, which
            # itself uses the model's standardised features — so the model
            # shapes the ranking, not just the absolute score level.
            scores[action_id] = round(
                0.6 * propensity + 0.4 * _affinity(action_id, member, model), 4)
            rules_applied[action_id] = _rules_for(
                action_id, member, self.max_contacts_per_week)
        eligible = [a for a in candidates if not rules_applied[a["id"]]]
        chosen = None
        if eligible:
            # Highest score wins; candidate order breaks ties.
            chosen = max(eligible, key=lambda a: scores[a["id"]])["id"]
        return {
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "member_id": member["member_id"],
            "chosen_action": chosen,
            "model_version": version,
            "model_propensity": round(propensity, 4),
            "scores": scores,
            "rules_applied": rules_applied,
            "reason": "no eligible action" if chosen is None else "highest scored eligible action",
        }

    def decide_with_baseline(self, member, candidates=None, timestamp=None):
        """Like decide(), but also records the rule-only baseline action.

        The baseline is what a fixed priority ordering would have picked
        for the same member, so outcome_report() can compare the
        model-chosen decisions against it on the same members.
        """
        decision = self.decide(member, candidates=candidates, timestamp=timestamp)
        decision["baseline_action"] = baseline_action(
            member, candidates=candidates,
            max_contacts_per_week=self.max_contacts_per_week)
        return decision


def log_decision(path, decision):
    """Append one decision dict to a JSONL log file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(decision) + "\n")
    return path


def read_decisions(path):
    """Read a JSONL decision log back into a list of dicts."""
    if not os.path.exists(path):
        return []
    decisions = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                decisions.append(json.loads(line))
    return decisions


def outcome_report(decisions, outcomes):
    """Join logged decisions with outcomes and summarise acceptance.

    `outcomes` is a list of {"member_id", "action", "accepted"} dicts.
    Returns per-action acceptance rates plus a comparison of the
    model-chosen decisions against the rule-only baseline, using the
    "baseline_action" recorded on each decision by
    `DecisioningEngine.decide_with_baseline` (decisions without one are
    left out of the baseline column).
    """
    by_key = {(o["member_id"], o["action"]): bool(o["accepted"]) for o in outcomes}
    per_action = {}
    model_accepted, model_total = 0, 0
    baseline_accepted, baseline_total = 0, 0
    for d in decisions:
        member_id = d["member_id"]
        chosen = d["chosen_action"]
        if chosen is None:
            continue
        accepted = by_key.get((member_id, chosen))
        if accepted is None:
            continue
        stats = per_action.setdefault(chosen, {"decisions": 0, "accepted": 0})
        stats["decisions"] += 1
        stats["accepted"] += int(accepted)
        model_total += 1
        model_accepted += int(accepted)
        baseline = d.get("baseline_action")
        if baseline is not None:
            baseline_accepted_outcome = by_key.get((member_id, baseline))
            if baseline_accepted_outcome is not None:
                baseline_total += 1
                baseline_accepted += int(baseline_accepted_outcome)
    for stats in per_action.values():
        stats["acceptance_rate"] = round(
            stats["accepted"] / stats["decisions"], 4) if stats["decisions"] else 0.0
    model_rate = round(model_accepted / model_total, 4) if model_total else None
    baseline_rate = round(baseline_accepted / baseline_total, 4) if baseline_total else None
    return {
        "per_action": per_action,
        "model_chosen": {"decisions": model_total, "accepted": model_accepted,
                         "acceptance_rate": model_rate},
        "rule_only_baseline": {"decisions": baseline_total, "accepted": baseline_accepted,
                               "acceptance_rate": baseline_rate},
        "lift_vs_baseline": (
            round(model_rate - baseline_rate, 4)
            if model_rate is not None and baseline_rate is not None else None),
    }
