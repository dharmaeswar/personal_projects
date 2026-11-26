"""Demo: run one multi-agent research question end to end."""

import json

from research_platform.orchestrator import ResearchRun
from research_platform.observability import log_run

QUESTION = "What is the momentum signal and what did the momentum factor return?"


def main():
    result = ResearchRun(QUESTION).run()
    print(result["answer"]["text"])
    print()
    print("Citations:", ", ".join(result["answer"]["citations"]))
    validation = result["validation"]
    print("Validation passed:", validation["passed"] if validation else None)
    print("Tools used:", ", ".join(result["tools_used"]))
    print("Steps used:", result["steps_used"])
    log_run("research_runs.jsonl", result)
    print("Run logged to research_runs.jsonl")


if __name__ == "__main__":
    main()
