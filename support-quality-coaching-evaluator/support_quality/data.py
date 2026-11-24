"""Curated data: quality rubric, human-labeled support cases, the
help-center knowledge base, and agent-training simulation scenarios.

Everything is synthetic demo data. No real customers, cases, or policies.
"""

from dataclasses import dataclass, field

# ---------------------------------------------------------------- rubric

@dataclass(frozen=True)
class Criterion:
    key: str
    label: str
    weight: float
    description: str


RUBRIC = [
    Criterion("accuracy", "Accuracy", 0.30,
              "The answer states the correct policy facts and no wrong facts."),
    Criterion("empathy", "Empathy", 0.15,
              "The agent acknowledges the guest/host impact and is courteous."),
    Criterion("policy_compliance", "Policy compliance", 0.25,
              "The answer follows the stated policy and never promises what "
              "the policy forbids."),
    Criterion("resolution", "Resolution", 0.20,
              "The case ends with a concrete next step or a resolved outcome."),
    Criterion("clarity", "Clarity", 0.10,
              "The answer is short, plain, and free of jargon or confusion."),
]

PASS_OVERALL = 1.4   # weighted overall score (0-2 scale) needed to pass
PASS_MIN_CRITERION = 1  # no criterion may score 0 on a passing case


# ------------------------------------------------------- knowledge base

@dataclass(frozen=True)
class KBArticle:
    article_id: str
    title: str
    body: str


KB_ARTICLES = [
    KBArticle("kb-cancel-48h", "Cancellation within 48 hours",
              "A guest may cancel within 48 hours of booking for a full "
              "refund, provided the check-in date is at least 14 days away. "
              "After 48 hours the host cancellation policy applies."),
    KBArticle("kb-extenuating", "Extenuating circumstances",
              "Extenuating circumstances cover unexpected events such as a "
              "natural disaster, a serious illness, or government travel "
              "restrictions. The guest must provide documentation and the "
              "case is reviewed by a specialist team."),
    KBArticle("kb-refund-timeline", "Refund timelines",
              "Approved refunds return to the original payment method "
              "within 5 to 15 business days. The exact timing depends on "
              "the guest's bank. Refunds are never issued as cash or gift "
              "cards."),
    KBArticle("kb-host-payout", "Host payouts",
              "Host payouts are released 24 hours after the guest checks in. "
              "A payout can be held when a case is open or when the "
              "reservation is under review for a policy violation."),
    KBArticle("kb-resolution-center", "Resolution Center requests",
              "Guests and hosts can open a Resolution Center request for "
              "money issues such as damage, extra cleaning, or a refund. "
              "Requests must be filed within 60 days of checkout and both "
              "sides have 72 hours to respond."),
    KBArticle("kb-safety", "Guest safety and urgent issues",
              "If a guest reports an unsafe stay, the agent must escalate "
              "to the safety team immediately and offer rebooking help. "
              "Never ask the guest to stay in a place they say is unsafe."),
]


# ------------------------------------------------------------- cases

@dataclass
class SupportCase:
    case_id: str
    scenario: str
    transcript: list  # list of (speaker, text); speaker in {"guest", "agent"}
    human_labels: dict  # criterion key -> 0, 1, or 2
    required_facts: list = field(default_factory=list)  # facts a correct answer must state
    forbidden_claims: list = field(default_factory=list)  # claims the policy forbids


CASES = [
    SupportCase(
        "case-001",
        "Guest asks to cancel 30 hours after booking; check-in is 20 days away.",
        [("guest", "I booked yesterday and need to cancel. Can I get a full refund?"),
         ("agent", "Of course — I understand plans change and I'm sorry for the trouble. "
                   "Because you booked within the last 48 hours and check-in is more than "
                   "14 days away, you qualify for a full refund to your original payment "
                   "method. I've cancelled the reservation and the refund will arrive "
                   "within 5 to 15 business days.")],
        {"accuracy": 2, "empathy": 2, "policy_compliance": 2, "resolution": 2, "clarity": 2},
        required_facts=["48 hours", "14 days", "full refund", "5 to 15 business days"],
    ),
    SupportCase(
        "case-002",
        "Guest wants a cash refund instead of a refund to the card.",
        [("guest", "My refund was approved. Can you send it as cash instead?"),
         ("agent", "Sure, I can send the refund as cash to your address. "
                   "It should reach you in a few days.")],
        {"accuracy": 0, "empathy": 1, "policy_compliance": 0, "resolution": 0, "clarity": 1},
        required_facts=["original payment method", "5 to 15 business days"],
        forbidden_claims=["cash"],
    ),
    SupportCase(
        "case-003",
        "Host asks why a payout is held while a damage case is open.",
        [("guest", "My payout is missing. The guest checked in two days ago."),
         ("agent", "Thanks for flagging this. I can see a damage case is open on this "
                   "reservation, which holds the payout until the case is reviewed. "
                   "Payouts are normally released 24 hours after check-in, and yours "
                   "will be released once the case closes. I'll keep you updated here.")],
        {"accuracy": 2, "empathy": 1, "policy_compliance": 2, "resolution": 2, "clarity": 2},
        required_facts=["24 hours", "case is open", "payout"],
    ),
    SupportCase(
        "case-004",
        "Guest reports an unsafe stay and asks what to do.",
        [("guest", "The lock on the door is broken and I don't feel safe staying here."),
         ("agent", "I'm really sorry — your safety comes first, and I understand how "
                   "worrying this is. I've escalated this to our safety team right now "
                   "and I can help you rebook somewhere safe tonight. You do not need "
                   "to stay there.")],
        {"accuracy": 2, "empathy": 2, "policy_compliance": 2, "resolution": 2, "clarity": 2},
        required_facts=["safety team", "rebook"],
        forbidden_claims=["stay there"],
    ),
    SupportCase(
        "case-005",
        "Guest files a Resolution Center request 70 days after checkout.",
        [("guest", "I want to claim cleaning costs from a stay 70 days ago."),
         ("agent", "No problem, I can open that request for you right away and the host "
                   "will have 72 hours to respond.")],
        {"accuracy": 0, "empathy": 1, "policy_compliance": 0, "resolution": 1, "clarity": 1},
        required_facts=["60 days"],
        forbidden_claims=["open that request"],
    ),
    SupportCase(
        "case-006",
        "Guest asks when an approved refund will arrive.",
        [("guest", "My refund was approved yesterday. When will I see the money?"),
         ("agent", "Approved refunds return to your original payment method within 5 to "
                   "15 business days, depending on your bank. I'll monitor it and let "
                   "you know if anything changes.")],
        {"accuracy": 2, "empathy": 1, "policy_compliance": 2, "resolution": 2, "clarity": 2},
        required_facts=["original payment method", "5 to 15 business days"],
    ),
    SupportCase(
        "case-007",
        "Guest claims extenuating circumstances but offers no documentation.",
        [("guest", "There was a storm and I couldn't travel. I want a full refund."),
         ("agent", "I'm sorry your trip was disrupted. Extenuating circumstances can "
                   "cover events like a natural disaster, but the case needs "
                   "documentation and a specialist review. If you can share the "
                   "documentation, I'll open the review for you right away.")],
        {"accuracy": 2, "empathy": 2, "policy_compliance": 2, "resolution": 1, "clarity": 2},
        required_facts=["documentation", "specialist"],
    ),
    SupportCase(
        "case-008",
        "Agent gives a long, jargon-heavy answer about a payout hold.",
        [("guest", "Where is my payout?"),
         ("agent", "Per the disbursement cadence and the open adjudication workflow on "
                   "the reservation ledger, the remittance is pending finalisation of "
                   "the dispute resolution pipeline and will be effectuated subsequent "
                   "to closure, subject to the applicable temporal parameters.")],
        {"accuracy": 1, "empathy": 0, "policy_compliance": 1, "resolution": 0, "clarity": 0},
        required_facts=["24 hours", "case"],
    ),
]


# ------------------------------------------------- simulation scenarios

@dataclass(frozen=True)
class SimulationScenario:
    scenario_id: str
    title: str
    persona: str
    opening: str
    expected_facts: list
    forbidden_claims: list


SIMULATION_SCENARIOS = [
    SimulationScenario(
        "sim-cancel-late",
        "Late cancellation, no refund window",
        "Guest booked 10 days ago; check-in is in 3 days; wants a full refund.",
        "I booked 10 days ago and now I need to cancel. I want all my money back.",
        ["host cancellation policy", "48 hours"],
        ["full refund"],
    ),
    SimulationScenario(
        "sim-unsafe-stay",
        "Guest feels unsafe at check-in",
        "Guest arrived to find a broken front door lock at night.",
        "I just arrived and the front door doesn't lock. I'm alone and scared.",
        ["safety team", "rebook"],
        ["stay there"],
    ),
    SimulationScenario(
        "sim-payout-hold",
        "Host payout delayed by an open case",
        "Host's payout is 5 days late; a damage claim is open.",
        "My payout is five days late. I need that money for my mortgage.",
        ["24 hours", "case is open", "payout"],
        [],
    ),
]


def check_dataset():
    """Completeness check: every case carries a human label on every
    rubric criterion, and every scenario names its expected facts."""
    problems = []
    keys = {c.key for c in RUBRIC}
    for case in CASES:
        missing = keys - set(case.human_labels)
        if missing:
            problems.append(f"{case.case_id}: missing labels {sorted(missing)}")
        bad = {k: v for k, v in case.human_labels.items()
               if v not in (0, 1, 2)}
        if bad:
            problems.append(f"{case.case_id}: labels out of range {bad}")
    for scenario in SIMULATION_SCENARIOS:
        if not scenario.expected_facts:
            problems.append(f"{scenario.scenario_id}: no expected facts")
    return problems
