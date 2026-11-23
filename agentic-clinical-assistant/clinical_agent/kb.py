"""Synthetic knowledge base and patient roster.

Everything here is invented demo data for a portfolio project. No real
patients, no real clinical guidance, no real health records.
"""

KNOWLEDGE_BASE = [
    {
        "doc_id": "KB-001",
        "title": "Diabetes follow-up care",
        "text": (
            "For adults with type 2 diabetes, check HbA1c every 3 to 6 months "
            "until the target below 7 percent is met, then every 6 months. "
            "Review blood pressure, kidney function, foot health and medication "
            "adherence at each follow-up visit. Escalate to the care team when "
            "HbA1c rises above 9 percent or the patient reports frequent "
            "hypoglycemia."
        ),
    },
    {
        "doc_id": "KB-002",
        "title": "Hypertension medication review",
        "text": (
            "Review blood pressure readings and medication adherence for "
            "hypertension at every visit. If systolic pressure stays above "
            "140 despite adherence, consider a dose review with the prescribing "
            "clinician. Ask about dizziness, cough and ankle swelling, and "
            "record home readings when the patient brings them."
        ),
    },
    {
        "doc_id": "KB-003",
        "title": "Post-discharge check-in",
        "text": (
            "Contact the patient within 48 hours of a hospital discharge. "
            "Confirm the discharge medication list, check for new symptoms "
            "such as fever, chest pain or shortness of breath, and confirm the "
            "follow-up appointment is booked. Escalate urgently when the "
            "patient reports chest pain, severe breathlessness or confusion."
        ),
    },
    {
        "doc_id": "KB-004",
        "title": "Referral criteria for cardiology",
        "text": (
            "Refer to cardiology when a patient has new chest pain on exertion, "
            "an abnormal ECG, uncontrolled hypertension with organ damage, or "
            "heart failure symptoms such as breathlessness when lying flat. "
            "Include recent blood pressure readings, medication list and ECG "
            "results with the referral."
        ),
    },
    {
        "doc_id": "KB-005",
        "title": "Vaccination schedule for adults",
        "text": (
            "Offer the annual influenza vaccine each autumn, a COVID booster "
            "when due, and the pneumococcal vaccine for adults over 65 or with "
            "chronic conditions such as diabetes. Record the vaccine, batch "
            "and date given, and remind the patient of the next due date."
        ),
    },
    {
        "doc_id": "KB-006",
        "title": "Medication adherence support",
        "text": (
            "When a patient misses doses, ask about cost, side effects and "
            "daily routine before changing the prescription. Pill organizers, "
            "phone reminders and simpler dosing schedules improve adherence. "
            "Document the adherence plan and review it at the next visit."
        ),
    },
]

PATIENTS = {
    "P-1001": {
        "name": "Alice Johnson",
        "dob": "03/14/1962",
        "mrn": "MRN-482913",
        "phone": "716-555-0142",
        "email": "alice.johnson@example.org",
        "conditions": ["type 2 diabetes", "hypertension"],
        "medications": ["metformin 500mg twice daily", "lisinopril 10mg daily"],
        "last_visit": "2026-10-28",
        "risk_flags": ["HbA1c 8.4 percent at last visit"],
    },
    "P-1002": {
        "name": "Robert Chen",
        "dob": "11/02/1958",
        "mrn": "MRN-917204",
        "phone": "716-555-0187",
        "email": "robert.chen@example.org",
        "conditions": ["hypertension", "high cholesterol"],
        "medications": ["amlodipine 5mg daily", "atorvastatin 20mg daily"],
        "last_visit": "2026-11-05",
        "risk_flags": [],
    },
    "P-1003": {
        "name": "Maria Garcia",
        "dob": "07/25/1971",
        "mrn": "MRN-335871",
        "phone": "716-555-0119",
        "email": "maria.garcia@example.org",
        "conditions": ["type 2 diabetes"],
        "medications": ["metformin 850mg twice daily"],
        "last_visit": "2026-09-30",
        "risk_flags": ["missed last two follow-up visits"],
    },
}
