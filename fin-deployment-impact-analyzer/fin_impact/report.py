"""Reports: customer-facing deployment summary + product feedback loop.

The customer summary states the measured impact in plain language
with the uncertainty attached. The feedback loop turns the same
numbers into product input: which channels underperform, where
escalations cluster, and what to fix next.
"""

from . import stats


def customer_summary(customer, metrics, handle_test, esc_uplift):
    """Plain-language impact summary for one customer."""
    after = metrics["after"]
    before = metrics["before"]
    lines = [
        f"Fin deployment impact — {customer}",
        f"Conversations measured: {before['conversations']} before, "
        f"{after['conversations']} after.",
        f"Resolution rate: {before['resolution_rate']} before -> "
        f"{after['resolution_rate']} after "
        f"(uplift {esc_uplift['uplift']}, 95% CI "
        f"{esc_uplift['ci_low']} to {esc_uplift['ci_high']}).",
        f"Mean handle time: {before['mean_handle_minutes']} min before "
        f"-> {after['mean_handle_minutes']} min after "
        f"(Welch t={handle_test['t']}, p={handle_test['p_value']}).",
        f"Escalation rate: {before['escalation_rate']} before -> "
        f"{after['escalation_rate']} after.",
        f"Mean CSAT: {before['mean_csat']} before -> "
        f"{after['mean_csat']} after.",
    ]
    return "\n".join(lines) + "\n"


def product_feedback(channel_rows, metrics):
    """Feedback-loop notes for the product team, from the same numbers."""
    notes = []
    worst = min(channel_rows, key=lambda r: r["resolution_rate"])
    notes.append(
        f"Lowest-resolution channel after deployment: {worst['channel']} "
        f"({worst['resolution_rate']} over {worst['conversations']} "
        f"conversations) — prioritise knowledge-base coverage there.")
    after = metrics["after"]
    if after["escalation_rate"] > 0.10:
        notes.append(
            f"Escalation rate after deployment is still "
            f"{after['escalation_rate']} — review the top escalation "
            f"intents with the customer before scaling further.")
    if after["mean_csat"] is not None and after["mean_csat"] < 4.0:
        notes.append(
            f"Mean CSAT after deployment is {after['mean_csat']} — "
            f"check whether resolved-by-Fin conversations score lower "
            f"than human-handled ones.")
    if not notes:
        notes.append("No product flags: all channels above the bar and "
                     "escalation and CSAT within guardrails.")
    return notes


def compare_arms(conversations):
    """Before/after handle-time test + resolution uplift, from raw rows."""
    before = [c.handle_minutes for c in conversations
              if c.period == "before"]
    after = [c.handle_minutes for c in conversations
             if c.period == "after"]
    handle_test = stats.welch_t_test(before, after)
    n_b = len(before)
    n_a = len(after)
    res_b = sum(1 for c in conversations
                if c.period == "before" and c.resolved_by_fin)
    res_a = sum(1 for c in conversations
                if c.period == "after" and c.resolved_by_fin)
    esc_uplift = stats.uplift(res_b / max(n_b, 1), res_a / max(n_a, 1),
                              n_b, n_a)
    return handle_test, esc_uplift
