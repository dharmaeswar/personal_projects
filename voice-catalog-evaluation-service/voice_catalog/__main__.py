"""Run the voice catalog + evaluation service.

Usage: python -m voice_catalog [port]
"""
import sys

from voice_catalog.server import main

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
