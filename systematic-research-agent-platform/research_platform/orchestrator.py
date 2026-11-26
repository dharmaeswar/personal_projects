"""Orchestrator: the long-horizon multi-agent research loop.

One research run is: plan -> retrieve -> execute -> compose -> validate.
If validation fails and steps remain in the budget, the run re-retrieves
once with a broader query and recomposes before giving up. The full
trajectory (every agent step and tool call) is returned with the answer,
so the evaluation harness can score the run instead of only its output.
"""

from .agents import plan, retrieve, execute, compose, validate
from .corpus import get_documents
from .knowledge_layer import KnowledgeLayer
from .tools import ToolRegistry


class ResearchRun:
    """A single multi-agent research run with a step budget."""

    def __init__(self, question, use_validator=True, step_budget=12):
        self.question = question
        self.use_validator = use_validator
        self.step_budget = step_budget
        self.trajectory = []

    def run(self):
        knowledge = KnowledgeLayer(get_documents())
        tools = ToolRegistry(knowledge)
        steps_used = 0

        subtasks = plan(self.question)
        self.trajectory.append({"agent": "planner", "subtasks": subtasks})
        steps_used += 1

        evidence = []
        computations = []
        for subtask in subtasks:
            evidence += retrieve(tools, subtask)
            computations += execute(tools, subtask)
            steps_used += 2
        self.trajectory.append({
            "agent": "retriever+executor",
            "evidence_docs": sorted({e.get("doc_id") for e in evidence if e.get("doc_id")}),
            "computations": computations,
        })

        answer = compose(self.question, subtasks, evidence, computations)
        self.trajectory.append({"agent": "composer", "answer": answer["text"]})

        validation = None
        if self.use_validator:
            validation = validate(tools, answer)
            self.trajectory.append({"agent": "validator", "validation": validation})
            steps_used += 1
            if not validation["passed"] and steps_used < self.step_budget:
                # One repair pass: broader retrieval, then recompose + revalidate.
                extra = tools.call("search_knowledge", {"query": self.question})
                evidence += [e for e in extra if e.get("doc_id") not in
                             {x.get("doc_id") for x in evidence}]
                answer = compose(self.question, subtasks, evidence, computations)
                validation = validate(tools, answer)
                self.trajectory.append({"agent": "validator-repair",
                                        "validation": validation})

        return {
            "question": self.question,
            "answer": answer,
            "validation": validation,
            "trajectory": self.trajectory,
            "tool_calls": tools.call_log,
            "tools_used": sorted({c["tool"] for c in tools.call_log}),
            "steps_used": steps_used,
        }
