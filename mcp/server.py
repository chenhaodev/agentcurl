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

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# allow running from a bare checkout (no `pip install -e .` needed)
sys.path.insert(0, os.path.join(_REPO, "src"))

# load the repo's own .env regardless of the launcher's cwd, so secrets
# (DEEPSEEK_API_KEY etc.) live in .env and not in the MCP client config
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_REPO, ".env"))
except Exception:
    pass

from agentcurl.mcp import main  # noqa: E402

if __name__ == "__main__":
    main()
