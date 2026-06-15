"""Jina backend — r.jina.ai reader. Zero-install remote URL -> markdown.

Prepends the target URL to https://r.jina.ai/ and gets clean, LLM-ready markdown
back. No browser, no API key required (a JINA_API_KEY raises rate limits). The
remote service handles JS rendering, so it's a good zero-dependency fallback for
dynamic pages when you can't install Playwright. Only implements `fetch`; the
CrawlMixin walks links for `crawl` (links come from the markdown via httpx on the
real page when needed, but jina returns markdown without a link list, so crawl
on jina is shallow by nature).
"""

from __future__ import annotations

from .base import CrawlMixin
from ..config import Config
from ..fetch_utils import http_get
from ..types import Document


class JinaBackend(CrawlMixin):
    name = "jina"

    def __init__(self, config: Config):
        self.config = config

    def fetch(self, url: str, **opts) -> Document:
        headers = {
            "Accept": "text/markdown",
            # ask the reader for structured extras in response headers/body
            "X-With-Links-Summary": "true",
        }
        if self.config.jina_api_key:
            headers["Authorization"] = f"Bearer {self.config.jina_api_key}"

        reader_url = f"{self.config.jina_base_url.rstrip('/')}/{url}"
        resp = http_get(reader_url, self.config, extra_headers=headers)
        # On an error status (429 rate-limit, 4xx/5xx) the body is an error
        # message, not page content — drop it to empty markdown so a router
        # fallback chain moves on to the next backend instead of accepting it.
        markdown = resp.text if resp.status_code < 400 else ""
        title = _first_heading(markdown)
        return Document(
            url=url,
            status=resp.status_code,
            markdown=markdown,
            html="",  # reader returns markdown only
            title=title,
            links=[],  # link-summary parsing left to crawl4ai/firecrawl tiers
            metadata={"backend": self.name, "reader_url": reader_url},
        )


def _first_heading(markdown: str) -> str:
    """Title = first markdown '# ' heading (the reader puts 'Title:' there)."""
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("Title:"):
            return line[len("Title:"):].strip()
        if line.startswith("# "):
            return line[2:].strip()
    return ""
