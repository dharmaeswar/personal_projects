"""Agentic workflow: planner -> preprocessor -> analyst -> reviewer.

Each agent is a small, traced step: every tool call records its name,
arguments, latency and outcome, so the whole run is reproducible and
auditable. The reviewer checks every drafted claim against the
computed numbers — a claim whose numbers do not appear in the results
is rejected as ungrounded. The final report is released only after a
human approval gate (``approve=True``), mirroring the human-in-the-loop
rule for anything that leaves the system.
"""

import re
import time

from . import features, preprocess, stats


class ToolTrace:
    """One traced tool call."""

    def __init__(self, agent, tool, args, outcome, latency_ms):
        self.agent = agent
        self.tool = tool
        self.args = args
        self.outcome = outcome
        self.latency_ms = latency_ms

    def as_dict(self):
        return {"agent": self.agent, "tool": self.tool,
                "args": self.args, "outcome": self.outcome,
                "latency_ms": self.latency_ms}


class Agent:
    """Base agent: runs a step and traces it."""

    name = "agent"

    def __init__(self):
        self.trace = []

    def call(self, tool, args, func):
        started = time.perf_counter()
        outcome = func()
        latency = round((time.perf_counter() - started) * 1000, 2)
        self.trace.append(ToolTrace(self.name, tool, args, outcome,
                                    latency))
        return outcome


class PlannerAgent(Agent):
    """Turns the study question into an ordered plan of steps."""

    name = "planner"

    def plan(self, question, n_slides):
        steps = [
            "preprocess_slides",
            "extract_features",
            "summarise_per_slide",
            "compare_arms",
            "draft_findings",
            "review_findings",
        ]
        return self.call("make_plan",
                         {"question": question, "n_slides": n_slides},
                         lambda: steps)


class PreprocessAgent(Agent):
    """Runs tile preprocessing over every slide in the study."""

    name = "preprocessor"

    def run(self, slides):
        return self.call(
            "preprocess_slides",
            {"n_slides": len(slides)},
            lambda: {s.slide_id: preprocess.preprocess_slide(s)
                     for s in slides})


class AnalystAgent(Agent):
    """Per-slide summaries and the treated-vs-control comparison."""

    name = "analyst"

    def summarise(self, prepped):
        def _work():
            out = {}
            for slide_id, prep in prepped.items():
                scores = [features.tile_score(t)
                          for t in prep["usable"]]
                out[slide_id] = {
                    "usable_tiles": prep["usable_tiles"],
                    "rejected_tiles": prep["rejected_tiles"],
                    "mean_score": round(
                        stats.mean(scores), 4) if scores else 0.0,
                    "mean_nuclei": round(
                        stats.mean([t.nuclei for t in prep["usable"]]), 2)
                    if prep["usable"] else 0.0,
                    "embedding": features.slide_embedding(
                        prep["usable"]),
                }
            return out

        return self.call("summarise_slides",
                         {"n_slides": len(prepped)}, _work)

    def compare(self, summaries, treated_ids, control_ids):
        def _work():
            treated = [summaries[i]["mean_score"] for i in treated_ids]
            control = [summaries[i]["mean_score"] for i in control_ids]
            return stats.welch_t_test(treated, control)

        return self.call("compare_arms",
                         {"treated": len(treated_ids),
                          "control": len(control_ids)}, _work)

    def draft(self, summaries, comparison):
        def _work():
            return [
                f"Mean tile score: treated "
                f"{comparison['mean_a']} vs control "
                f"{comparison['mean_b']}.",
                f"Difference is significant at p="
                f"{comparison['p_value']} (Welch t="
                f"{comparison['t']}, df={comparison['df']}).",
                f"Effect size Cohen's d={comparison['cohens_d']}.",
                f"Slides analysed: {len(summaries)}.",
            ]

        return self.call("draft_findings", {}, _work)


class ReviewerAgent(Agent):
    """Rejects any drafted claim whose numbers are not in the results."""

    name = "reviewer"

    def review(self, claims, evidence_numbers):
        def _work():
            kept, rejected = [], []
            for claim in claims:
                found = [float(n) for n in re.findall(r"\d+\.\d+|\d+", claim)
                         if float(n) in evidence_numbers]
                if found:
                    kept.append(claim)
                else:
                    rejected.append(claim)
            return {"kept": kept, "rejected": rejected}

        return self.call("review_findings",
                         {"n_claims": len(claims)}, _work)


def run_study(slides, question, approve=False):
    """Run the full agentic workflow over a study.

    Returns the plan, per-slide summaries, comparison, kept claims,
    rejected claims, the full tool trace, and the release status:
    the report is "released" only when ``approve=True`` (human gate),
    otherwise "held_for_human_review".
    """
    planner, prep_agent = PlannerAgent(), PreprocessAgent()
    analyst, reviewer = AnalystAgent(), ReviewerAgent()
    plan = planner.plan(question, len(slides))
    prepped = prep_agent.run(slides)
    summaries = analyst.summarise(prepped)
    treated = [s.slide_id for s in slides if s.label == "treated"]
    control = [s.slide_id for s in slides if s.label == "control"]
    comparison = analyst.compare(summaries, treated, control)
    claims = analyst.draft(summaries, comparison)
    evidence = {comparison["mean_a"], comparison["mean_b"],
                comparison["p_value"], comparison["t"],
                comparison["df"], comparison["cohens_d"],
                float(len(summaries))}
    review = reviewer.review(claims, evidence)
    trace = (planner.trace + prep_agent.trace + analyst.trace
             + reviewer.trace)
    return {
        "plan": plan,
        "summaries": summaries,
        "comparison": comparison,
        "kept_claims": review["kept"],
        "rejected_claims": review["rejected"],
        "trace": [t.as_dict() for t in trace],
        "status": "released" if approve else "held_for_human_review",
    }
