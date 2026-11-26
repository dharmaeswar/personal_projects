"""Demo: ask the marketing RAG service three questions and print the
answers with citations, agent trace and validation results.
"""
from marketing_rag.service import MarketingRagService

QUESTIONS = [
    "Which campaign has the best return on spend?",
    "Which audience segment should the LinkedIn ABM pilot target?",
    "Where should we move budget from the weakest campaign?",
]


def main() -> None:
    service = MarketingRagService()
    for question in QUESTIONS:
        result = service.ask(question)
        print("=" * 78)
        print("Q:", question)
        print("A:", result["answer"])
        print("Citations:", [c["id"] for c in result["citations"]])
        print("Intents:", result["intents"])
        print("Validation passed:", result["validation"]["passed"],
              "| unsupported:", result["validation"]["unsupported"])
        if result["derived"]["budget_suggestion"]:
            print("Derived suggestion:", result["derived"]["budget_suggestion"])


if __name__ == "__main__":
    main()
