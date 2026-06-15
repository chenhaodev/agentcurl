"""agentcurl MCP server — a thin stdio wrapper over CrawlManager.

Exposes three tools to any MCP client (Claude Code / Claude Desktop):
  agentcurl_fetch(url)              -> one page as markdown + metadata
  agentcurl_crawl(url, depth, ...)  -> same-domain crawl, one summary per page
  agentcurl_extract(url, schema|prompt) -> DeepSeek structured JSON

The backend is whatever CRAWL_BACKEND selects, so the MCP inherits every tier.
Run with:  python -m agentcurl.mcp   (or via mcp/server.py)

Requires the MCP SDK:  pip install "mcp[cli]"
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from .manager import CrawlManager


def _doc_summary(doc) -> dict:
    """Compact dict — full markdown plus cheap stats, no giant raw HTML blob."""
    d = dataclasses.asdict(doc)
    d.pop("html", None)  # keep payloads small; markdown is the useful surface
    d["markdown_chars"] = len(doc.markdown)
    d["link_count"] = len(doc.links)
    return d


def build_server():
    """Construct the FastMCP server. Imported lazily so the package itself has
    no hard dependency on the MCP SDK."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            'agentcurl MCP server needs the MCP SDK. Run: pip install "mcp[cli]"'
        ) from e

    mcp = FastMCP("agentcurl")
    manager = CrawlManager()

    @mcp.tool()
    def agentcurl_fetch(url: str) -> str:
        """Fetch one web page and return its clean markdown + metadata as JSON.

        Args:
            url: The absolute URL to fetch.
        """
        doc = manager.fetch(url)
        return json.dumps(_doc_summary(doc), ensure_ascii=False)

    @mcp.tool()
    def agentcurl_crawl(url: str, depth: int = 1, max_pages: int = 20) -> str:
        """Crawl a site starting at `url`, following same-domain links.

        Args:
            url: The absolute start URL.
            depth: Link-following depth (default 1).
            max_pages: Hard cap on pages fetched (default 20).
        """
        docs = manager.crawl(url, depth=depth, max_pages=max_pages)
        return json.dumps([_doc_summary(d) for d in docs], ensure_ascii=False)

    @mcp.tool()
    def agentcurl_extract(url: str, schema: str) -> str:
        """Extract structured data from a page using DeepSeek.

        Args:
            url: The absolute URL to extract from.
            schema: Either a JSON object string mapping field -> type
                (e.g. '{"title":"str","price":"number"}') or a plain
                natural-language instruction (e.g. "the title and author").
        """
        target: Any
        try:
            parsed = json.loads(schema)
            target = parsed if isinstance(parsed, (dict, list)) else schema
        except (json.JSONDecodeError, TypeError):
            target = schema  # treat as a natural-language prompt
        res = manager.extract(url, target)
        return json.dumps(dataclasses.asdict(res), ensure_ascii=False)

    return mcp


def main() -> None:
    build_server().run()  # stdio transport by default


if __name__ == "__main__":
    main()
