"""End-to-end demo: run the member-context streaming pipeline and print
the run manifest. No real Kafka, cloud, or member data is involved.
"""

from member_context.orchestration import manifest_json, run_pipeline


def main() -> None:
    manifest, layers = run_pipeline()
    print(manifest_json(manifest))
    print()
    print(f"Snapshot rows: {len(layers['snapshots'])}")
    print(f"LLM documents: {len(layers['llm_documents'])}")
    print(f"Quarantined rows: {len(layers['quarantined'])}")
    if layers["snapshots"]:
        print("Sample snapshot row:", layers["snapshots"][0])
    if layers["llm_documents"]:
        print("Sample LLM document:", layers["llm_documents"][0])


if __name__ == "__main__":
    main()
