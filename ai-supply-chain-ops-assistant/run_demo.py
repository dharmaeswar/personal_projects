"""End-to-end demo: knowledge, analytics, workflow draft + approval, eval."""

from ai_ops.analytics import answer as analytics_answer
from ai_ops.evaluate import run_eval
from ai_ops.knowledge import answer as knowledge_answer
from ai_ops.workflows import WorkflowStore, draft_reorders


def main():
    print("== Knowledge discovery ==")
    for q in (
        "How is the reorder point calculated?",
        "What do we do when a delivery carton count does not match the shipping notice?",
        "What discount do employees get on pet insurance?",
    ):
        result = knowledge_answer(q)
        print(f"Q: {q}")
        print(f"A: {result['answer']}")
        print(f"   sources: {[s['id'] for s in result['sources']]} abstained={result['abstained']}")

    print("\n== Analytics ==")
    for q in ("What is the fill rate?", "Which SKUs are in stockout?", "Which rows have low cover?"):
        result = analytics_answer(q)
        print(f"Q: {q}\nA: {result['answer']}\n   method: {result['method']}")

    print("\n== Workflow automation (human review required) ==")
    store = WorkflowStore()
    tasks, created = draft_reorders(store)
    print(f"Drafted {len(tasks)} reorder tasks ({created} new).")
    for task in tasks:
        print(f"  {task['id']} [{task['status']}] {task['sku']} at {task['warehouse']}: {task['detail']}")
    if tasks:
        approved = store.review(tasks[0]["id"], approve=True, reviewer="operator-demo")
        print(f"Human approved {approved['id']}; the rest stay drafts until reviewed.")
        print(f"Audit log: {store.audit}")

    print("\n== AI evaluation (representative tasks) ==")
    report = run_eval()
    print(f"Passed {report['passed']}/{report['total']} (pass rate {report['pass_rate']}).")
    for r in report["results"]:
        print(f"  {'PASS' if r['passed'] else 'FAIL'} {r['id']}: {r['note']}")


if __name__ == "__main__":
    main()
