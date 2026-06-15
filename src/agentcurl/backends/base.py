"""The common crawl-backend contract.

Every crawler (httpx+trafilatura, Playwright, crawl4ai, Firecrawl, jina) is
wrapped to satisfy this Protocol. The interface is intentionally the lowest
common denominator — `fetch` one page, `crawl` a site — so switching backends is
a one-line config change. Backend-specific superpowers surface through
`Document.metadata` rather than widening this contract.

`CrawlMixin.crawl` gives every backend a same-domain breadth-first walk built on
its own `fetch`, so backends that only know how to fetch one page (static, jina)
still crawl. Backends with native deep-crawl (crawl4ai, firecrawl) override it.
"""

from __future__ import annotations

from collections import deque
from typing import Protocol, runtime_checkable

from ..config import Config
from ..fetch_utils import RateLimiter, RobotsGate, same_domain
from ..types import Document


@runtime_checkable
class CrawlBackend(Protocol):
    name: str

    def fetch(self, url: str, **opts) -> Document:
        """One page -> markdown + html + metadata."""
        ...

    def crawl(self, url: str, *, depth: int = 1, max_pages: int = 20, **opts) -> list[Document]:
        """Breadth-first same-domain crawl starting at `url`."""
        ...


class CrawlMixin:
    """Default `crawl` via same-domain breadth-first `fetch`.

    Mix into any backend that implements `fetch`. Honors robots.txt and the
    rate-limit delay from config, dedupes URLs, and never exceeds `max_pages`.
    Subclasses with native deep-crawl simply define their own `crawl`.
    """

    config: Config

    def fetch(self, url: str, **opts) -> Document:  # pragma: no cover - contract stub
        raise NotImplementedError

    def crawl(
        self, url: str, *, depth: int = 1, max_pages: int = 20, **opts
    ) -> list[Document]:
        robots = RobotsGate(self.config)
        limiter = RateLimiter(self.config.rate_limit_delay)
        seen: set[str] = {url}
        queue: deque[tuple[str, int]] = deque([(url, 0)])
        out: list[Document] = []

        while queue and len(out) < max_pages:
            current, level = queue.popleft()
            if not robots.allowed(current):
                continue
            limiter.wait()
            try:
                doc = self.fetch(current, **opts)
            except Exception as e:
                out.append(
                    Document(url=current, status=0, metadata={"error": repr(e)})
                )
                continue
            out.append(doc)
            if level >= depth:
                continue
            for link in doc.links:
                if link not in seen and same_domain(link, url):
                    seen.add(link)
                    queue.append((link, level + 1))
        return out[:max_pages]
