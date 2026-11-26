"""Databricks Claims Data Platform — synthetic healthcare member/claims lakehouse.

Runs locally with pandas + Parquet. It does NOT pretend a Spark cluster ran:
every pandas operation names the Databricks/Spark operation it mirrors, so the
same logic maps one-to-one onto a real Databricks job. See README.md.
"""
