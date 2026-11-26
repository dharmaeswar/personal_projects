"""Power BI semantic-model export for the gold HEDIS tables.

The JD asks for Power BI datasets and data models, including row-level
security. There is no Power BI service here, so the project exports the
model definition as JSON — tables, columns, DAX measures, relationships
and an RLS role — in the shape a Power BI dataset definition carries.
The test suite validates that every measure references a real table and
column and that the RLS role filters on a real column, so the export is
structurally sound even though it was never published to the service.
"""

import json
from pathlib import Path


def build_semantic_model():
    return {
        "name": "Payer HEDIS Monthly",
        "tables": [
            {"name": "DimMember",
             "columns": ["member_id", "sex", "age", "plan", "diabetes",
                         "hypertension"],
             "source": "gold_hedis_monthly via silver_members"},
            {"name": "FactClaim",
             "columns": ["claim_id", "member_id", "service_date",
                         "diag_code", "procedure_code", "paid_amount"],
             "source": "silver_claims"},
            {"name": "HedisMonthly",
             "columns": ["measure", "measurement_month", "denominator",
                         "numerator", "rate"],
             "source": "gold_hedis_monthly"},
        ],
        "measures": [
            {"name": "Total Paid",
             "dax": "SUM(FactClaim[paid_amount])"},
            {"name": "Claim Count",
             "dax": "COUNTROWS(FactClaim)"},
            {"name": "HEDIS Rate",
             "dax": "DIVIDE(SUM(HedisMonthly[numerator]),"
                    " SUM(HedisMonthly[denominator]))"},
            {"name": "BCS Rate",
             "dax": "CALCULATE([HEDIS Rate],"
                    " HedisMonthly[measure] = \"BCS\")"},
            {"name": "COL Rate",
             "dax": "CALCULATE([HEDIS Rate],"
                    " HedisMonthly[measure] = \"COL\")"},
            {"name": "CDC Control Rate",
             "dax": "CALCULATE([HEDIS Rate],"
                    " HedisMonthly[measure] = \"CDC\")"},
            {"name": "CBP Control Rate",
             "dax": "CALCULATE([HEDIS Rate],"
                    " HedisMonthly[measure] = \"CBP\")"},
        ],
        "relationships": [
            {"from": "FactClaim[member_id]", "to": "DimMember[member_id]",
             "cardinality": "many-to-one"},
            {"from": "HedisMonthly[measurement_month]",
             "to": "FactClaim[service_date]", "cardinality": "many-to-many",
             "note": "month grain; join on FORMAT(service_date, 'yyyy-MM')"},
        ],
        "roles": [
            {"name": "Plan viewers",
             "table": "DimMember",
             "filter": "DimMember[plan] = USERPRINCIPALNAME()",
             "note": "Row-level security: a viewer sees only their own"
                     " plan's members. Placeholder expression — bind to"
                     " the real identity provider before publishing."},
        ],
    }


def write_semantic_model(path):
    model = build_semantic_model()
    Path(path).write_text(json.dumps(model, indent=2))
    return model
