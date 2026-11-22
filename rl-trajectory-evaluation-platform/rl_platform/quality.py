"""Task quality review: rubric scoring, verdicts and reviewer agreement.

Every task (one unit of training data) is reviewed against a five-point
rubric. A task passes only when its mean score is at least 4 and no rubric
item scores below 3; anything else goes back for fixes or is quarantined.
"""

RUBRIC = ["instruction_clarity", "solvability", "reward_correctness", "no_leakage", "coverage"]
PASS_MEAN = 4.0
MIN_ITEM = 3


def create_task(store, env_id, instruction, reference_answer=None):
    from .store import next_id

    if env_id not in store["environments"]:
        return None, ["environment %s not found" % env_id]
    if not instruction or not str(instruction).strip():
        return None, ["instruction is required"]
    task_id = next_id(store, "task")
    task = {
        "id": task_id,
        "env_id": env_id,
        "instruction": instruction,
        "reference_answer": reference_answer,
        "status": "unreviewed",
    }
    store["tasks"][task_id] = task
    return task, []


def review_task(store, task_id, reviewer, scores, notes=""):
    """Score a task on the rubric; returns the review with its verdict."""
    from .store import next_id

    task = store["tasks"].get(task_id)
    if task is None:
        return None, ["task %s not found" % task_id]
    missing = [item for item in RUBRIC if item not in scores]
    if missing:
        return None, ["missing rubric scores: %s" % ", ".join(missing)]
    bad = [item for item, value in scores.items() if not isinstance(value, int) or not 1 <= value <= 5]
    if bad:
        return None, ["scores must be integers 1-5: %s" % ", ".join(bad)]
    mean = sum(scores[item] for item in RUBRIC) / len(RUBRIC)
    verdict = "pass" if mean >= PASS_MEAN and min(scores.values()) >= MIN_ITEM else "needs_work"
    review_id = next_id(store, "review")
    review = {
        "id": review_id,
        "task_id": task_id,
        "reviewer": reviewer,
        "scores": {item: scores[item] for item in RUBRIC},
        "mean_score": round(mean, 2),
        "verdict": verdict,
        "notes": notes,
    }
    store["reviews"][review_id] = review
    task["status"] = "approved" if verdict == "pass" else "needs_work"
    return review, []


def task_quality(task_id, reviews):
    """Aggregate all reviews for one task: mean score and final verdict."""
    mine = [r for r in reviews if r["task_id"] == task_id]
    if not mine:
        return {"task_id": task_id, "review_count": 0, "mean_score": None, "verdict": "unreviewed"}
    mean = sum(r["mean_score"] for r in mine) / len(mine)
    verdict = "pass" if all(r["verdict"] == "pass" for r in mine) else "needs_work"
    return {"task_id": task_id, "review_count": len(mine), "mean_score": round(mean, 2), "verdict": verdict}


def reviewer_agreement(reviews):
    """Share of reviewer pairs that agree on the verdict, per task."""
    by_task = {}
    for review in reviews:
        by_task.setdefault(review["task_id"], []).append(review["verdict"])
    pairs, agree = 0, 0
    for verdicts in by_task.values():
        for i in range(len(verdicts)):
            for j in range(i + 1, len(verdicts)):
                pairs += 1
                if verdicts[i] == verdicts[j]:
                    agree += 1
    if pairs == 0:
        return {"pairs": 0, "agreement_rate": None}
    return {"pairs": pairs, "agreement_rate": round(agree / pairs, 3)}


def quarantine_defects(store):
    """Tasks whose latest review failed, with the failing rubric items."""
    out = []
    for task in store["tasks"].values():
        if task["status"] != "needs_work":
            continue
        reviews = [r for r in store["reviews"].values() if r["task_id"] == task["id"]]
        failing = sorted({item for r in reviews for item, v in r["scores"].items() if v < MIN_ITEM})
        out.append({"task_id": task["id"], "env_id": task["env_id"], "failing_items": failing})
    return out
