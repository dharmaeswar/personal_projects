"""Simulation environments: train agents on realistic support scenarios.

A session plays one scripted scenario. The trainee agent replies turn by
turn; each reply is scored against the rubric with the same judge used
for real cases, so training scores and production quality scores are
comparable. The session ends with a coaching plan built from the
turn-by-turn evidence.
"""

from dataclasses import dataclass, field

from .data import SIMULATION_SCENARIOS, SupportCase
from .judge import RuleBasedJudge
from .coaching import build_coaching_plan


@dataclass
class TurnScore:
    turn: int
    reply: str
    overall: float
    scores: dict
    passed: bool


@dataclass
class SimulationReport:
    scenario_id: str
    title: str
    turns: list  # list of TurnScore
    mean_overall: float
    coaching_plan: object = None


class SimulationSession:
    """One trainee practising one scenario."""

    def __init__(self, scenario_id, judge=None):
        scenario = next((s for s in SIMULATION_SCENARIOS
                         if s.scenario_id == scenario_id), None)
        if scenario is None:
            raise ValueError(f"unknown scenario: {scenario_id}")
        self.scenario = scenario
        self.judge = judge or RuleBasedJudge("v1")
        self.turns = []

    def reply(self, text):
        """Score one trainee reply and record it."""
        case = SupportCase(
            case_id=f"{self.scenario.scenario_id}-turn-{len(self.turns) + 1}",
            scenario=self.scenario.title,
            transcript=[("guest", self.scenario.opening),
                        ("agent", text)],
            human_labels={},
            required_facts=list(self.scenario.expected_facts),
            forbidden_claims=list(self.scenario.forbidden_claims),
        )
        result = self.judge.grade(case)
        self.turns.append(TurnScore(len(self.turns) + 1, text,
                                    result.overall, result.scores,
                                    result.passed))
        return result

    def finish(self):
        if not self.turns:
            raise ValueError("no replies recorded; cannot finish an empty session")
        mean_overall = round(
            sum(t.overall for t in self.turns) / len(self.turns), 3)
        # Coaching plan from the weakest turn's full judge result.
        worst = min(self.turns, key=lambda t: t.overall)
        case = SupportCase(
            case_id=f"{self.scenario.scenario_id}-turn-{worst.turn}",
            scenario=self.scenario.title,
            transcript=[("guest", self.scenario.opening),
                        ("agent", worst.reply)],
            human_labels={},
            required_facts=list(self.scenario.expected_facts),
            forbidden_claims=list(self.scenario.forbidden_claims),
        )
        plan = build_coaching_plan(self.judge.grade(case),
                                   case_id=self.scenario.scenario_id)
        return SimulationReport(self.scenario.scenario_id, self.scenario.title,
                                list(self.turns), mean_overall, plan)
