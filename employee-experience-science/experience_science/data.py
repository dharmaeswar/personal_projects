"""Synthetic employee-experience dataset (deterministic, seed fixed).

One row per employee: organisation, shift, tenure, manager tenure,
weekly overtime, monthly schedule changes, experience and wellbeing
scores (1-5), an attrition flag, and one open-ended feedback comment
with a known true theme. Effects are planted on purpose so the
analysis can be checked against ground truth:

- night shift lowers experience by ~0.5
- overtime above 10 h/week lowers wellbeing and experience
- a new manager (< 1 year) lowers experience by ~0.4
- 4+ schedule changes a month raises attrition risk
"""

import random

ORGS = ["Fulfillment", "Sortation", "Delivery", "Corporate", "Tech"]
SHIFTS = ["Day", "Night"]

FEEDBACK_TEMPLATES = {
    "workload": [
        "The workload this month has been too heavy and overtime keeps growing.",
        "Too many overtime hours, I barely get time to rest between shifts.",
        "Workload is unmanageable, we need more people on the team.",
        "I am tired all the time and dread coming to work each morning.",
    ],
    "schedule": [
        "My schedule keeps changing with almost no notice and it ruins my plans.",
        "Shift changes are announced too late, I cannot plan childcare.",
        "The rotating schedule is unpredictable and exhausting.",
        "I never know when I am working next week and it wears me down.",
    ],
    "manager": [
        "My new manager does not listen and gives unclear direction.",
        "I have had three managers this year and none of them know my work.",
        "My manager never gives feedback on my performance.",
        "Nobody tells me anything about how I am doing or what is expected.",
    ],
    "pay": [
        "Pay does not match the work we do, especially on night shifts.",
        "I expected a raise this year and the pay review felt unfair.",
        "The pay is too low for the hours and the physical effort.",
    ],
    "growth": [
        "There is no clear path to grow or get promoted from my role.",
        "I want training and a chance to move into a different team.",
        "Career growth here feels blocked, nobody talks about next steps.",
    ],
    "tools": [
        "The tools we use crash daily and slow down every task.",
        "Our scanners and software are outdated and waste so much time.",
        "The system is slow and the tools break whenever we need them most.",
    ],
}


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def generate(n=1200, seed=42):
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        org = rng.choices(ORGS, weights=[0.35, 0.25, 0.20, 0.10, 0.10])[0]
        shift = "Night" if rng.random() < 0.30 else "Day"
        tenure = round(rng.uniform(0.1, 12.0), 1)
        manager_tenure = round(rng.uniform(0.1, 8.0), 1)
        overtime = _clamp(rng.gauss(6.0, 3.0) + (2.0 if shift == "Night" else 0.0), 0, 20)
        overtime = round(overtime, 1)
        sched_changes = rng.choices([0, 1, 2, 3, 4, 5, 6], weights=[25, 25, 20, 15, 8, 4, 3])[0]

        experience = 3.8 + rng.gauss(0, 0.6)
        if shift == "Night":
            experience -= 0.5
        if overtime > 10:
            experience -= 0.4
        if manager_tenure < 1.0:
            experience -= 0.4
        if sched_changes >= 4:
            experience -= 0.3
        experience = _clamp(round(experience, 2), 1.0, 5.0)

        wellbeing = 3.9 + rng.gauss(0, 0.6)
        wellbeing -= 0.05 * max(0.0, overtime - 6.0)
        if sched_changes >= 4:
            wellbeing -= 0.2
        wellbeing = _clamp(round(wellbeing, 2), 1.0, 5.0)

        p_attr = 0.05
        if experience < 2.8:
            p_attr += 0.35
        if overtime > 12:
            p_attr += 0.15
        if sched_changes >= 4:
            p_attr += 0.10
        attrition = 1 if rng.random() < p_attr else 0

        theme = rng.choice(list(FEEDBACK_TEMPLATES))
        comment = rng.choice(FEEDBACK_TEMPLATES[theme])

        rows.append({
            "employee_id": f"E{i + 1:05d}",
            "org": org,
            "shift": shift,
            "tenure_years": tenure,
            "manager_tenure_years": manager_tenure,
            "overtime_hours_week": overtime,
            "schedule_changes_month": sched_changes,
            "experience_score": experience,
            "wellbeing_score": wellbeing,
            "attrition": attrition,
            "feedback_theme": theme,
            "feedback_text": comment,
        })
    return rows
