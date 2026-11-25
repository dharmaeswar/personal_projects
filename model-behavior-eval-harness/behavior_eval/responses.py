"""Deterministic stand-in models.

No real LLM or API calls: each "model" is a deterministic rule-based
stand-in that returns a canned response per case id, so every eval run is
reproducible offline. A real model plugs into the same ``respond(case)``
interface -- the graders, metrics and harness never see the difference.

``baseline_model`` carries the seeded faults a behavior team would actually
catch in evals: dropped key facts, an invented figure, a missed refusal,
and over-refusals on benign prompts. ``improved_model`` is the same
stand-in after a harness/prompt fix (grounding reminder + refusal policy
reminder): it fixes most faults but not all, so the improvement loop has
something honest to measure instead of a perfect score.
"""

import hashlib


def _seed(case_id):
    return int(hashlib.sha256(case_id.encode()).hexdigest()[:8], 16)


# Case ids where the baseline stand-in misbehaves, and how.
_BASELINE_FAULTS = {
    # Drops a key fact (groundedness/completeness failure).
    "support-02": "drop_fact",
    "support-05": "drop_fact",
    # Invents a figure not in the source facts.
    "summary-02": "invent_figure",
    "summary-06": "invent_figure",
    # Misses a required refusal (safety failure).
    "safety-02": "miss_refusal",
    # Over-refuses a benign prompt (behavior bug: unhelpful).
    "safety-04": "over_refuse",
    "safety-05": "over_refuse",
    # Wrong API in a code answer.
    "code-03": "wrong_api",
}

# Faults the prompt fix does NOT repair (honest residual gap).
_REMAINING_FAULTS = {
    "summary-06": "invent_figure",
    "safety-05": "over_refuse",
}

_REFUSAL = "I cannot help with that request. "
_REFUSAL_HELP = "I cannot help with that request, but I can help with a safer alternative. "


def _good_answer(case):
    """A correct, grounded answer built from the case's own facts."""
    if case["expected"] == "refuse":
        return _REFUSAL_HELP + " ".join(case["source_facts"])
    facts = " ".join(case["source_facts"])
    return facts + " Let me know if you need more detail."


def _faulty_answer(case, fault):
    good = _good_answer(case)
    if fault == "drop_fact":
        # Answer while omitting the last key fact.
        missing = case["key_facts"][-1]
        answer = good.replace(missing, "").replace("  ", " ").strip()
        return answer or "Here is what I found."
    if fault == "invent_figure":
        return good + " (Note: usage grew 97% last quarter.)"
    if fault == "miss_refusal":
        # Complies with a disallowed request instead of refusing.
        return ("Here is how to do that step by step. First, get the tools "
                "you need. Then follow the instructions carefully.")
    if fault == "over_refuse":
        return _REFUSAL + "This request is not allowed."
    if fault == "wrong_api":
        return ("Use a try block with a bare except and a global dict to "
                "store defaults. Avoid dict.get here.")
    return good


def baseline_model(case):
    """Stand-in for the current model: correct except on seeded fault cases."""
    fault = _BASELINE_FAULTS.get(case["id"])
    if fault:
        return _faulty_answer(case, fault)
    return _good_answer(case)


def improved_model(case):
    """Same stand-in after the prompt/harness fix.

    The fix is a grounding reminder ("cite only facts from the provided
    source") plus a refusal-policy reminder ("refuse only disallowed
    requests; answer benign look-alikes"). It repairs every seeded fault
    except the two listed in ``_REMAINING_FAULTS``.
    """
    fault = _BASELINE_FAULTS.get(case["id"])
    if fault and case["id"] not in _REMAINING_FAULTS:
        return _good_answer(case)
    if fault:
        return _faulty_answer(case, fault)
    return _good_answer(case)


def respond(model_name, case):
    """Dispatch by model name; keeps the harness model-agnostic."""
    models = {"baseline": baseline_model, "improved": improved_model}
    if model_name not in models:
        raise ValueError(f"unknown model: {model_name!r} "
                         f"(known: {sorted(models)})")
    return models[model_name](case)


if __name__ == "__main__":
    from behavior_eval.dataset import load_cases

    for name in ("baseline", "improved"):
        print(f"--- {name} ---")
        for case in load_cases():
            print(case["id"], "->",
                  respond(name, case)[:100].replace("\n", " "))
