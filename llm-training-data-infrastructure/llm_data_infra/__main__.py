"""Run the LLM training-data infrastructure server: python -m llm_data_infra."""
from .server import run
from .store import Store

if __name__ == "__main__":
    run(Store("llm_data_infra.db"))
