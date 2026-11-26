"""Start the marketing RAG REST API (default http://127.0.0.1:8000)."""
import sys

from marketing_rag.api import run_server

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port)
