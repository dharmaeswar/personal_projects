# LLM Rollout Toolkit

A small, typed Python library for LLM sampling, post-training and
evaluation: chat-template rendering, tool-call parsing, session
management with context compaction, a rollout-loop runtime, graders,
a reference tokenizer with parity checks, and semantic-versioning
helpers.

Built as a portfolio project for a Software Engineer, Frameworks &
Libraries application (packaging model-launch code into open-source
core libraries: renderers, tokenizers, tool-call handling, rollout
loops, graders). All prompts, tools and grades are synthetic demo
data; nothing here describes a real model or real user data. Python
standard library only — no third-party runtime dependencies.

## What it does

- **Rendering** (`llm_rollout/render.py`) — render system / user /
  assistant / tool messages into a ChatML-style prompt; parse
  `<tool_call>{...json...}</tool_call>` blocks out of assistant text,
  skipping malformed blocks and reporting them.
- **Tokenizer** (`llm_rollout/tokenizer.py`) — a tiny deterministic
  tokenizer (words + punctuation) for token budgets and token-level
  parity checks against another encoder. It is a reference
  implementation, not a BPE tokenizer.
- **Sessions** (`llm_rollout/session.py`) — message history with a
  token budget; `compact()` drops the oldest turns and inserts a short
  summary record so the session fits the budget again.
- **Rollout loop** (`llm_rollout/rollout.py`) — drive a step function
  through tool calls: parse, execute registered tools, append results,
  compact when over budget, stop on a final answer or the step limit;
  the full transcript is returned for inspection and grading.
- **Graders** (`llm_rollout/graders.py`) — exact-match, regex,
  keyword-coverage and numeric-closeness graders, each returning a
  score in [0, 1] with a reason; `combine()` takes a weighted mean.
- **Versioning** (`llm_rollout/versioning.py`) — semantic-version
  parsing and bumps, plus a `@deprecated` decorator that warns callers.

## Run it

```bash
python run_demo.py            # scripted rollout: calculator tool, graded answer
python -m pytest tests/ -q    # 9 tests
```

Example:

```python
from llm_rollout import graders, render, rollout, session

sess = session.Session("You are helpful.", token_budget=200)
sess.add("user", "What is 17 * 6 + 4?")
result = rollout.run_rollout(sess, model_step_fn, {"calculator": calc})
grade = graders.exact_match("The answer is 106.", result["final_answer"])
```

Demo: a scripted model calls the calculator tool once, answers 106 in
2 steps, and grades 1.0 on exact match + keyword coverage.
