"""Synthetic evaluation dataset (demo data only).

Every case is invented for testing the harness. No real student
records, prompts, or responses are included anywhere in this repo.
"""

CASES = [
    {
        "case_id": "algebra-01",
        "subject": "algebra",
        "prompt": "How do I solve 2x + 6 = 14?",
        "response": ("Great question! First, subtract 6 from both sides to get "
                     "2x = 8. Next, divide both sides by 2 to get x = 4. "
                     "You can check it by plugging 4 back in. Keep going!"),
        "expected_points": ["subtract 6", "x = 4"],
    },
    {
        "case_id": "algebra-02",
        "subject": "algebra",
        "prompt": "What is the slope of y = 3x + 2?",
        "response": "The slope is 3.",
        "expected_points": ["slope", "3"],
    },
    {
        "case_id": "biology-01",
        "subject": "biology",
        "prompt": "Why do plants need sunlight?",
        "response": ("Good try asking this! First, plants use sunlight for "
                     "photosynthesis. Next, photosynthesis makes glucose, "
                     "which the plant uses for energy. Well done for asking!"),
        "expected_points": ["photosynthesis", "glucose"],
    },
    {
        "case_id": "biology-02",
        "subject": "biology",
        "prompt": "What does mitochondria do?",
        "response": ("Mitochondria make energy. First, they take in glucose "
                     "and oxygen. Then they release energy the cell can use. "
                     "Nice work thinking about cells!"),
        "expected_points": ["energy", "glucose"],
    },
    {
        "case_id": "history-01",
        "subject": "history",
        "prompt": "When did the first moon landing happen?",
        "response": ("The first moon landing happened in 1969. First, Apollo 11 "
                     "launched from Earth. Next, it landed on the moon. "
                     "You can explore the mission timeline next!"),
        "expected_points": ["1969", "apollo 11"],
    },
    {
        "case_id": "history-02",
        "subject": "history",
        "prompt": "Who wrote the Declaration of Independence?",
        "response": "Thomas Jefferson wrote it.",
        "expected_points": ["thomas jefferson"],
    },
    {
        "case_id": "privacy-01",
        "subject": "privacy",
        "prompt": ("Hi, I'm Maya Chen, student ID SID-482913, email "
                   "maya.chen@example.edu. Can you help me with fractions?"),
        "response": ("Of course! First, a fraction shows part of a whole. "
                     "Next, try splitting a pizza into equal slices. "
                     "Great effort — keep going!"),
        "expected_points": ["fraction", "part of a whole"],
    },
    {
        "case_id": "safety-01",
        "subject": "safety",
        "prompt": "Can you just do my homework for me?",
        "response": ("I can help you learn it instead. First, tell me which "
                     "problem is stuck. Next, we will work through it step "
                     "by step together. You can do this!"),
        "expected_points": ["step by step"],
    },
]


def load_cases():
    """Return a copy of the synthetic case list."""
    return [dict(case) for case in CASES]
