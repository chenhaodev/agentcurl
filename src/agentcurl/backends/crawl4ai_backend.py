"""Crawl4AI backend — LLM-native self-host crawler: fit-markdown + deep crawl.

Crawl4AI renders pages (headless browser under the hood) and produces "fit"
markdown — a pruned, content-dense markdown tuned for LLM consumption — plus a
native breadth-first deep crawl. We drive its async API on one persistent event
loop so this adapter still satisfies the synchronous CrawlBackend Protocol, and
we OVERRIDE `crawl` to use its real deep-crawl instead of the link-walk mixin.

One `AsyncWebCrawler` (and the browser it manages) is started lazily and reused
across every `fetch`/`crawl`, then torn down in `close()` — a fresh per-call
crawler paid a browser launch each page. The shared loop is single-threaded, so
the link-walk fallback runs serially (`concurrent_fetch = False`).

Requires: pip install "crawl4ai" && crawl4ai-setup   (installs a browser once)
"""

from __future__ import annotations

import asyncio

from .base import CrawlMixin
from ..config import Config
from ..types import Document


class Crawl4AIBackend(CrawlMixin):
    name = "crawl4ai"
    concurrent_fetch = False  # one shared crawler on one event loop

    def __init__(self, config: Config):
        try:
            from crawl4ai import AsyncWebCrawler  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "crawl4ai backend selected but not installed. Run: "
                'pip install "agentcurl[crawl4ai]" && crawl4ai-setup'
            ) from e
        self.config = config
        self._loop = asyncio.new_event_loop()
        self._crawler = None  # started AsyncWebCrawler, reused across calls

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def _crawler_instance(self):
        """Start the crawler (and its browser) once and reuse it."""
        if self._crawler is None:
            from crawl4ai import AsyncWebCrawler

            self._crawler = AsyncWebCrawler()
            self._run(self._crawler.start())
        return self._crawler

    def close(self) -> None:
        """Tear down the reused crawler then close the loop. Safe to call twice."""
        if self._crawler is not None:
            if not self._loop.is_closed():
                try:
                    self._run(self._crawler.close())
                except Exception:
                    pass
            self._crawler = None  # drop the reference even if the loop is gone
        if self._loop is not None and not self._loop.is_closed():
            self._loop.close()

    def __del__(self):  # best-effort cleanup; don't raise during GC
        try:
            self.close()
        except Exception:
            pass

    def _to_document(self, result) -> Document:
        """Map a crawl4ai CrawlResult onto our Document."""
        md_obj = getattr(result, "markdown", None)
        markdown = ""
        if md_obj is not None:
            if self.config.crawl4ai_fit_markdown:
                markdown = getattr(md_obj, "fit_markdown", "") or getattr(
                    md_obj, "raw_markdown", ""
                )
            else:
                markdown = getattr(md_obj, "raw_markdown", "")
            if not markdown:
                markdown = str(md_obj)
        links_obj = getattr(result, "links", {}) or {}
        internal = [l.get("href", "") for l in links_obj.get("internal", [])]
        return Document(
            url=getattr(result, "url", ""),
            status=getattr(result, "status_code", 0) or 0,
            markdown=markdown,
            html=getattr(result, "html", "") or "",
            title=(getattr(result, "metadata", {}) or {}).get("title", ""),
            links=[l for l in internal if l],
            metadata={"backend": self.name, "success": getattr(result, "success", True)},
        )

    def fetch(self, url: str, **opts) -> Document:
        crawler = self._crawler_instance()
        return self._to_document(self._run(crawler.arun(url=url)))

    def crawl(
        self, url: str, *, depth: int = 1, max_pages: int = 20, **opts
    ) -> list[Document]:
        """Native deep crawl via crawl4ai's BFSDeepCrawlStrategy."""
        from crawl4ai import CrawlerRunConfig
        from crawl4ai.deep_crawling import BFSDeepCrawlStrategy

        strategy = BFSDeepCrawlStrategy(
            max_depth=depth, max_pages=max_pages, include_external=False
        )
        run_config = CrawlerRunConfig(deep_crawl_strategy=strategy, stream=False)

        crawler = self._crawler_instance()
        results = self._run(crawler.arun(url=url, config=run_config))
        if not isinstance(results, list):
            results = [results]
        return [self._to_document(r) for r in results][:max_pages]
