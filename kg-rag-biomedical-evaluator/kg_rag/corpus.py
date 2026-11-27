"""Seeded synthetic biomedical corpus and evaluation question set.

All documents are invented for this demo. No real literature, patients,
genes-as-facts, or company data is used. Sentences are written in the
relation patterns the extractor in graph.py recognises, so the graph
build is deterministic and reproducible.
"""

DOCUMENTS = [
    {
        "id": "D01",
        "title": "PARP inhibition in BRCA-mutated breast cancer",
        "text": (
            "Olaparib targets BRCA1. BRCA1 is associated with breast cancer. "
            "Olaparib treats breast cancer. BRCA1 is part of the DNA repair pathway. "
            "Patients with BRCA1 mutations show homologous recombination deficiency."
        ),
    },
    {
        "id": "D02",
        "title": "EGFR inhibition in non-small cell lung cancer",
        "text": (
            "Osimertinib targets EGFR. EGFR is associated with non-small cell lung cancer. "
            "Osimertinib treats non-small cell lung cancer. EGFR is part of the MAPK signaling pathway. "
            "EGFR mutations drive tumour growth in a subset of lung adenocarcinoma."
        ),
    },
    {
        "id": "D03",
        "title": "HER2-directed therapy in breast cancer",
        "text": (
            "Trastuzumab targets HER2. HER2 is associated with breast cancer. "
            "Trastuzumab treats breast cancer. HER2 interacts with EGFR. "
            "HER2 amplification is measured by immunohistochemistry and in situ hybridisation."
        ),
    },
    {
        "id": "D04",
        "title": "PD-1 blockade in melanoma",
        "text": (
            "Pembrolizumab targets PD-L1. PD-L1 is associated with melanoma. "
            "Pembrolizumab treats melanoma. PD-L1 is part of the immune checkpoint pathway. "
            "PD-L1 expression is measured as a tumour proportion score."
        ),
    },
    {
        "id": "D05",
        "title": "BRAF inhibition in melanoma",
        "text": (
            "Dabrafenib targets BRAF. BRAF is associated with melanoma. "
            "Dabrafenib treats melanoma. BRAF is part of the MAPK signaling pathway. "
            "BRAF V600E is the most common activating mutation in cutaneous melanoma."
        ),
    },
    {
        "id": "D06",
        "title": "TP53 and colorectal cancer",
        "text": (
            "TP53 is associated with colorectal cancer. TP53 is part of the DNA repair pathway. "
            "TP53 interacts with BRCA1. Loss of TP53 function is common in colorectal tumours. "
            "TP53 status is assessed by sequencing in the study cohort."
        ),
    },
    {
        "id": "D07",
        "title": "APOE and Alzheimer's disease",
        "text": (
            "APOE is associated with Alzheimer's disease. APOE interacts with amyloid-beta. "
            "Amyloid-beta is associated with Alzheimer's disease. "
            "Donanemab targets amyloid-beta. Donanemab treats Alzheimer's disease. "
            "APOE genotype stratifies risk in the observational cohort."
        ),
    },
    {
        "id": "D08",
        "title": "KRAS and colorectal cancer",
        "text": (
            "KRAS is associated with colorectal cancer. KRAS is part of the MAPK signaling pathway. "
            "KRAS interacts with BRAF. KRAS mutation status guides therapy selection in colorectal cancer. "
            "No approved drug in this corpus targets KRAS directly."
        ),
    },
    {
        "id": "D09",
        "title": "PI3K-AKT signalling in breast cancer",
        "text": (
            "PIK3CA is associated with breast cancer. PIK3CA is part of the PI3K-AKT signaling pathway. "
            "PIK3CA interacts with HER2. PIK3CA mutations co-occur with HER2 amplification in some tumours. "
            "The PI3K-AKT signaling pathway regulates cell growth and survival."
        ),
    },
    {
        "id": "D10",
        "title": "Immune checkpoint combinations in lung cancer",
        "text": (
            "Pembrolizumab treats non-small cell lung cancer. PD-L1 is associated with "
            "non-small cell lung cancer. Pembrolizumab targets PD-L1. "
            "Combination checkpoint blockade is under study in lung cancer cohorts."
        ),
    },
    {
        "id": "D11",
        "title": "DNA repair deficiency across tumours",
        "text": (
            "BRCA1 is associated with ovarian cancer. BRCA1 is part of the DNA repair pathway. "
            "Olaparib treats ovarian cancer. TP53 interacts with BRCA1. "
            "Homologous recombination deficiency is tested by genomic scar assays."
        ),
    },
    {
        "id": "D12",
        "title": "Amyloid clearance and cognition",
        "text": (
            "Donanemab targets amyloid-beta. Amyloid-beta is associated with Alzheimer's disease. "
            "Donanemab treats Alzheimer's disease. Tau is associated with Alzheimer's disease. "
            "Tau interacts with amyloid-beta. Cognitive decline is tracked with standardised scales."
        ),
    },
    {
        "id": "D13",
        "title": "Breast cancer screening and risk assessment",
        "text": (
            "BRCA1 testing is offered to families with a history of breast cancer. "
            "Mammography screening detects breast cancer early. "
            "Risk models estimate breast cancer probability from family history. "
            "Screening guidelines are updated annually by the review board."
        ),
    },
    {
        "id": "D14",
        "title": "Colorectal cancer screening and prevention",
        "text": (
            "Colorectal cancer screening reduces mortality in adults over 45. "
            "Genes associated with colorectal cancer risk are reviewed in the annual report. "
            "Colonoscopy finds colorectal cancer polyps before they progress. "
            "Screening intervals depend on family history and prior findings."
        ),
    },
    {
        "id": "D15",
        "title": "Lung cancer awareness and smoking cessation",
        "text": (
            "Non-small cell lung cancer accounts for most lung cancer cases. "
            "Smoking cessation lowers non-small cell lung cancer risk substantially. "
            "EGFR testing is discussed in the awareness brochure for non-small cell lung cancer. "
            "Public health campaigns target smoking in high-risk groups."
        ),
    },
]

# Each question names entities that live in the graph; `relevant` is the set
# of documents a correct answer must draw on. `expected_entities` are the
# answer's key entities, used by the groundedness / completeness check.
QUESTIONS = [
    {
        "id": "Q1",
        "question": "Which drug targets BRCA1-mutated breast cancer?",
        "relevant": {"D01"},
        "expected_entities": {"Olaparib", "BRCA1", "breast cancer"},
    },
    {
        "id": "Q2",
        "question": "Which drug treats non-small cell lung cancer by targeting EGFR?",
        "relevant": {"D02"},
        "expected_entities": {"Osimertinib", "EGFR", "non-small cell lung cancer"},
    },
    {
        "id": "Q3",
        "question": "Which drugs treat breast cancer, and which genes do they target?",
        "relevant": {"D01", "D03", "D09"},
        "expected_entities": {"Olaparib", "Trastuzumab", "BRCA1", "HER2"},
    },
    {
        "id": "Q4",
        "question": "Which drug targets PD-L1 and treats melanoma?",
        "relevant": {"D04"},
        "expected_entities": {"Pembrolizumab", "PD-L1", "melanoma"},
    },
    {
        "id": "Q5",
        "question": "Which gene is associated with Alzheimer's disease and interacts with amyloid-beta?",
        "relevant": {"D07", "D12"},
        "expected_entities": {"APOE", "amyloid-beta", "Alzheimer's disease"},
    },
    {
        "id": "Q6",
        "question": "Which pathway includes both EGFR and BRAF?",
        "relevant": {"D02", "D05"},
        "expected_entities": {"EGFR", "BRAF", "MAPK signaling pathway"},
    },
    {
        "id": "Q7",
        "question": "Which drug treats Alzheimer's disease by targeting amyloid-beta?",
        "relevant": {"D07", "D12"},
        "expected_entities": {"Donanemab", "amyloid-beta", "Alzheimer's disease"},
    },
    {
        "id": "Q8",
        "question": "Which genes are associated with colorectal cancer?",
        "relevant": {"D06", "D08"},
        "expected_entities": {"TP53", "KRAS", "colorectal cancer"},
    },
]
