"""Standalone entrypoint for the agentcurl MCP server.

The implementation lives in `agentcurl.mcp` (so `python -m agentcurl.mcp` works
on an installed package). This shim lets you run the server straight from a
checkout without installing — point your MCP client's `args` at this file:

    python mcp/server.py

Equivalent to `python -m agentcurl.mcp`.
"""

from __future__ import annotations

import os
import sys

# allow running from a bare checkout (no `pip install -e .` needed)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agentcurl.mcp import main  # noqa: E402

if __name__ == "__main__":
    main()
