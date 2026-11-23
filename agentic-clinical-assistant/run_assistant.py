"""Demo CLI for the Agentic Clinical Assistant.

Examples:
    python run_assistant.py
    python run_assistant.py --request "Review this patient's blood pressure medication." --patient P-1002
    python run_assistant.py --request "The patient reports chest pain." --patient P-1001 --approve
    python run_assistant.py --eval
"""

import argparse
import json
import sys

from clinical_agent.agent import Agent
from clinical_agent.evals import run_evals

DEFAULT_REQUEST = "When should this patient come back for diabetes follow-up?"
DEFAULT_PATIENT = "P-1001"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Agentic Clinical Assistant")
    parser.add_argument("--request", default=DEFAULT_REQUEST)
    parser.add_argument("--patient", default=DEFAULT_PATIENT)
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Simulate clinician approval for sends/escalations.",
    )
    parser.add_argument("--eval", action="store_true", help="Run the eval suite.")
    args = parser.parse_args(argv)

    if args.eval:
        results = run_evals()
        for result in results:
            status = "PASS" if result["passed"] else "FAIL"
            print(f"[{status}] {result['name']}")
            for failure in result["failures"]:
                print(f"       - {failure}")
        passed = sum(1 for r in results if r["passed"])
        print(f"{passed}/{len(results)} eval cases passed")
        return 0 if passed == len(results) else 1

    agent = Agent()
    result = agent.run(args.request, patient_id=args.patient, approve_send=args.approve)
    print("Answer:", result["answer"])
    print("Tools used:", ", ".join(result["tools_used"]))
    print(
        f"Escalated: {result['escalated']} | Sent: {result['sent']} | "
        f"Pending approval: {result['pending_approval']}"
    )
    print(json.dumps(result["audit"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
