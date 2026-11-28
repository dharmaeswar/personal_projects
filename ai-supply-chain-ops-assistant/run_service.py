"""Serve the AI Supply Chain Ops Assistant API + dashboard on port 8080."""

from ai_ops.service import run_server

if __name__ == "__main__":
    run_server(8080)
