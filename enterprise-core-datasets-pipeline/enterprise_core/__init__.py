"""Enterprise Core Datasets pipeline.

Builds the trusted datasets an Enterprise Core Datasets team owns: AI usage
and cost, Unit Economics (revenue vs cost drivers), Jira enterprise-application
data, and critical metrics (Gross Booking Value, Revenue).

Runs locally with pandas + Parquet. No Spark cluster, Airflow service, or
Iceberg runtime is involved, and the code says so where it matters. Every
pandas operation names the Spark operation it mirrors, so the same logic maps
one-to-one onto a real Spark job.
"""
