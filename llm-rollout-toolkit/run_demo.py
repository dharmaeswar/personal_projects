"""Demo: render a chat, run a tool-using rollout, grade the answer.

A scripted "model" answers a maths question by calling the calculator
tool, then gives the final answer. All data is synthetic.
Usage: python run_demo.py
"""
from llm_rollout import graders, render, rollout, session, tokenizer


def scripted_model(sess):
    # First step: call the calculator. Later steps: final answer.
    tool_msgs = [m for m in sess.messages if m["role"] == "tool"]
    if not tool_msgs:
        return render.format_tool_call(
            "calculator", {"expression": "17 * 6 + 4"})
    return "The answer is 106."


def calculator(expression: str) -> str:
    """Evaluate a simple arithmetic expression safely (numbers and
    + - * / only; anything else is rejected, never eval'd)."""
    import ast
    import operator

    ops = {ast.Add: operator.add, ast.Sub: operator.sub,
           ast.Mult: operator.mul, ast.Div: operator.truediv}

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        raise ValueError(f"unsupported expression: {expression!r}")

    return str(_eval(ast.parse(expression, mode="eval")))


if __name__ == "__main__":
    sess = session.Session(
        "You are a helpful assistant. Use tools when needed.", token_budget=200)
    sess.add("user", "What is 17 * 6 + 4?")
    print("prompt:\n" + render.render_chat(sess.messages))
    result = rollout.run_rollout(sess, scripted_model, {"calculator": calculator})
    print("steps:", result["steps"])
    print("final:", result["final_answer"])
    print("tokens:", result["tokens"])
    grade = graders.combine([
        graders.exact_match("The answer is 106.", result["final_answer"]),
        graders.keyword_coverage(["106"], result["final_answer"]),
    ])
    print("grade:", grade)
    print("parity:", tokenizer.parity_check(
        "Hello, world!", lambda t: tokenizer.encode(t))["parity"])
