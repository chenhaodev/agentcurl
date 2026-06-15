"""CrawlManager — the middleware facade tying backends + extraction together.

One object for the three surfaces (repo code, MCP server, SKILL) to drive:

    fetch(url)                 -> Document        one page via the active backend
    crawl(url, depth=...)      -> list[Document]  site walk (native or link-walk)
    extract(url|Document, ...) -> ExtractResult   DeepSeek -> validated JSON

The backend behind it is whatever CRAWL_BACKEND selects (a single backend or a
router chain); this class never imports a specific crawler, so switching
static<->browser<->crawl4ai<->firecrawl<->jina is a one-line config change.
"""

from __future__ import annotations

from typing import Any

from .backends import CrawlBackend, build_backend
from .config import Config
from .extract import Extractor
from .llm import DeepSeekLLM
from .types import Document, ExtractResult


class CrawlManager:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.from_env()
        self.llm = DeepSeekLLM(self.config)
        self.backend: CrawlBackend = build_backend(self.config)
        self.extractor = Extractor(self.llm)

    # -- crawl surface --------------------------------------------------------
    def fetch(self, url: str, **opts) -> Document:
        """Fetch one page as a Document via the active backend."""
        return self.backend.fetch(url, **opts)

    def crawl(
        self,
        url: str,
        *,
        depth: int | None = None,
        max_pages: int | None = None,
        **opts,
    ) -> list[Document]:
        """Crawl a site. Depth/max_pages default to config when omitted."""
        return self.backend.crawl(
            url,
            depth=self.config.crawl_depth if depth is None else depth,
            max_pages=self.config.crawl_max_pages if max_pages is None else max_pages,
            **opts,
        )

    # -- extraction surface ---------------------------------------------------
    def extract(self, source: str | Document, target: Any, **opts) -> ExtractResult:
        """Fetch (if given a URL) then run DeepSeek structured extraction.

        `target` is a dict schema ({"title": "str"}) or a natural-language
        prompt ("the article title and author"). Falls back to raw markdown with
        no DEEPSEEK_API_KEY, exactly like agentmem's offline path.
        """
        document = self.fetch(source, **opts) if isinstance(source, str) else source
        return self.extractor.extract(document, target)

    # -- lifecycle ------------------------------------------------------------
    def close(self) -> None:
        """Release backend resources (pooled connections, event loops). Safe to
        call multiple times; also runs on context-manager exit."""
        closer = getattr(self.backend, "close", None)
        if callable(closer):
            closer()

    def __enter__(self) -> "CrawlManager":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
