# LLM Interaction Primitives

A typed Python library of the model-interaction primitives a frameworks team
ships as open-source core libraries: chat-template rendering, tokenization,
tool-call parsing, session management with context compaction, a rollout
loop, graders, and semantic versioning with deprecation policy — plus the
token-level parity tests that let downstream users trust training and
sampling results.

Built as a portfolio project for the Thinking Machines Lab — Software
Engineer, Frameworks & Libraries application (Ashby
3882fc2b-6d28-4498-b6e3-ef53e22f8f03): packaging internal model-interaction
functionality into well-designed, well-documented public libraries with
clean composable typed APIs, versioning, changelogs, deprecation policies,
and release automation. All models, prompts, tool schemas and transcripts
here are synthetic demo data; nothing here describes a real model, a real
tokenizer vocabulary, or a real internal system. Python standard library
only at runtime; pytest for tests.

## What it does

- **Chat rendering** (`interaction_lib/rendering.py`) — typed `Message`
  objects rendered through named chat templates (ChatML-style and a plain
  `Role: content` template). Unknown roles and empty transcripts are
  rejected, not silently rendered; a generation prompt can be appended so
  the rendered text is ready for sampling.
- **Tokenizer** (`interaction_lib/tokenizer.py`) — a deterministic
  `SimpleTokenizer`: word/number/punctuation tokens, fixed special-token
  ids (`<|bos|>`, `<|eos|>`, `<|im_start|>`, `<|im_end|>`), stable
  first-seen id assignment, and an encode/decode round trip.
- **Tool-call parsing** (`interaction_lib/tool_calls.py`) — extracts tool
  calls from model text (fenced ```json blocks and `<tool_call>` blocks),
  and validates each call against a declared `ToolSpec`: known tool name,
  required parameters present, argument types checked.
- **Session & compaction** (`interaction_lib/session.py`) — a `Session`
  holds the message history, counts tokens with the tokenizer, and compacts
  to a token budget by dropping the oldest non-system turns first, keeping
  the system prompt and the most recent turns intact.
- **Rollout loop** (`interaction_lib/rollout.py`) — runs a sampler over a
  session until a stop string, a maximum turn count, or an empty reply;
  tool calls in a reply are executed through an injected executor and the
  results are appended as tool messages. The sampler is injected, so the
  loop is testable without any model.
- **Graders** (`interaction_lib/graders.py`) — `exact_match`,
  `json_validity`, and `tool_call_correctness` graders, each returning a
  score plus a short reason — the building blocks of an evaluation harness.
- **Versioning** (`interaction_lib/versioning.py`) — semver parsing and
  bumping, a `@deprecated` decorator that warns on use, and a changelog
  entry formatter, so a public release carries a version, a changelog, and
  a deprecation policy.
- **Parity checks** (`interaction_lib/parity.py`) — token-level parity:
  encodes text with this tokenizer and compares token-by-token against a
  reference encoder, reporting the first mismatch index.

## Usage

```bash
# Run the demo: render a chat, tokenize it, run a rollout, grade it
python run_demo.py

# Run the tests
python -m pytest tests/ -q
```

```python
from interaction_lib import Message, render_chat, SimpleTokenizer, Session
from interaction_lib import parse_tool_calls, run_rollout, grade_exact_match

tok = SimpleTokenizer()
msgs = [Message("system", "You are a helpful assistant."),
        Message("user", "What is 2 + 2?")]
prompt = render_chat(msgs, template="chatml", add_generation_prompt=True)
ids = tok.encode(prompt)
print(tok.decode(ids) == prompt)  # True — round trip

session = Session(messages=msgs, tokenizer=tok)
session.compact(max_tokens=40)
```

## Skills used

Only skills Dharma has verified: Python (typing, packaging, testing, CI),
pytest, Git/GitHub Actions, JSON, regular expressions. This project does
**not** claim PyTorch, Hugging Face, Rust/C++ extensions, or hands-on LLM
post-training (SFT/RL) experience — those are gaps for the role, stated
plainly in the application notes. The tokenizer here is a small
deterministic demo tokenizer, not a production BPE implementation.
