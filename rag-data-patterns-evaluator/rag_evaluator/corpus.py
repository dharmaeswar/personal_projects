"""Synthetic corpus: 10 short documents and 6 queries with known relevant docs.

The corpus is synthetic and hand-written so the evaluation is fully
deterministic and needs no downloads, credentials, or production data.
Each document covers one distinct data-engineering topic so retrieval
quality depends on chunking, not on topic overlap.
"""

DOCS = [
    {
        "id": "etl-pipelines",
        "title": "ETL pipelines",
        "text": (
            "ETL pipelines extract data from source systems, transform it with "
            "cleaning rules, and load it into a warehouse. "
            "Nightly batch jobs move pricing and market datasets into validation tables. "
            "Each load logs row counts and rejects bad records to a quarantine table. "
            "Pipeline owners check the load report every morning before reports ship."
        ),
    },
    {
        "id": "data-quality",
        "title": "Data quality checks",
        "text": (
            "Data quality checks flag missing values, duplicate keys, and out-of-range "
            "measures before reports ship. "
            "Rules run on every load and log each break with a severity rating. "
            "Stale feeds and broken keys are traced back to the source system. "
            "Clean data is the first gate; nothing downstream runs on failed checks."
        ),
    },
    {
        "id": "kafka-streaming",
        "title": "Kafka streaming",
        "text": (
            "Kafka streams usage events between billing and rating systems in real time. "
            "Producers publish events to topics and consumers process them in order. "
            "Streaming keeps subscriber balances current instead of waiting for a nightly batch. "
            "Event pipelines need retries and dead-letter queues when a consumer fails."
        ),
    },
    {
        "id": "model-validation",
        "title": "Model validation",
        "text": (
            "Model validation reprices derivatives with challenger models and compares "
            "each result with vendor marks. "
            "Greeks, curve construction, and day-count rules are checked one by one. "
            "Every break is logged with a severity rating and a reproducible test case. "
            "Validation notes record assumptions so a reviewer can repeat each finding."
        ),
    },
    {
        "id": "sql-tuning",
        "title": "SQL tuning",
        "text": (
            "SQL tuning rewrites slow queries, adds indexes, and partitions large tables. "
            "A query that scanned billions of rows now finishes in seconds after tuning. "
            "Explain plans show which step costs the most time on large datasets. "
            "Tuned queries keep dashboard refreshes fast and reliable for staff."
        ),
    },
    {
        "id": "data-modeling",
        "title": "Data modeling",
        "text": (
            "Logical and physical data models define tables, keys, and lineage from "
            "source to report. "
            "A good model keeps data integrity across pricing and reporting systems. "
            "Designers document each column so reviewers can trace a number to its source. "
            "Models are reviewed with analysts before any table is built."
        ),
    },
    {
        "id": "embeddings-genai",
        "title": "Embeddings for GenAI retrieval",
        "text": (
            "Retrieval augmented generation pairs a language model with a vector store "
            "of embedded document chunks. "
            "A user question is embedded the same way and the nearest chunks are fetched. "
            "The model answers from the fetched chunks instead of from memory alone. "
            "Good retrieval needs clean chunks and embeddings that match the question."
        ),
    },
    {
        "id": "chunking-strategies",
        "title": "Chunking strategies",
        "text": (
            "Chunking splits long documents into pieces for embedding and retrieval. "
            "Fixed-size chunks are simple but can cut a sentence in half. "
            "Sentence chunks keep meaning whole but vary in size. "
            "Overlapping windows repeat text at the edges so no idea is lost at a cut."
        ),
    },
    {
        "id": "airflow-scheduling",
        "title": "Airflow scheduling",
        "text": (
            "Airflow schedules pipeline tasks as directed acyclic graphs with retries "
            "and alerts. "
            "Each task runs in order and a failure blocks the tasks that depend on it. "
            "Scheduled runs replace manual nightly steps and alert the team on failure. "
            "Task logs show exactly which step broke and what it was doing."
        ),
    },
    {
        "id": "cloud-storage",
        "title": "Cloud object storage",
        "text": (
            "Object storage holds raw files in buckets and scales without servers to manage. "
            "Lakehouse tables add schema and transactions on top of stored files. "
            "Raw, cleaned, and curated zones separate untrusted input from trusted output. "
            "Storage costs stay low when old partitions are archived on a schedule."
        ),
    },
]

QUERIES = [
    {
        "id": "q1",
        "text": "how to clean data before loading it into a warehouse",
        "relevant": ["etl-pipelines", "data-quality"],
    },
    {
        "id": "q2",
        "text": "streaming events between systems in real time",
        "relevant": ["kafka-streaming"],
    },
    {
        "id": "q3",
        "text": "checking model prices against vendor marks",
        "relevant": ["model-validation"],
    },
    {
        "id": "q4",
        "text": "splitting documents into chunks for retrieval",
        "relevant": ["chunking-strategies", "embeddings-genai"],
    },
    {
        "id": "q5",
        "text": "scheduling pipeline tasks with retries and alerts",
        "relevant": ["airflow-scheduling"],
    },
    {
        "id": "q6",
        "text": "slow queries on large tables",
        "relevant": ["sql-tuning"],
    },
]
