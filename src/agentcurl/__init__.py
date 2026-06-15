"""agentcurl — a switchable web-crawler middleware.

One common interface over pluggable crawl backends (static httpx+trafilatura,
Playwright, crawl4ai, Firecrawl, jina), switched by a single env var, plus
DeepSeek-V4-Flash structured extraction — drivable from repo code, an MCP
server, or a Claude Code SKILL.

    from agentcurl import CrawlManager

    cm = CrawlManager()                          # backend chosen by CRAWL_BACKEND
    doc = cm.fetch("https://example.com")        # -> Document (markdown + links)
    result = cm.extract(doc, {"title": "str"})   # -> ExtractResult (JSON)
"""

from .config import Config
from .manager import CrawlManager
from .types import Document, ExtractResult

__all__ = ["CrawlManager", "Config", "Document", "ExtractResult"]
__version__ = "0.1.0"
