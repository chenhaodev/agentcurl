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

from concurrent.futures import ThreadPoolExecutor
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

    The walk proceeds level by level. Within a level the pages are independent,
    so they are fetched concurrently on a thread pool (sized by
    `Config.crawl_concurrency`) — the big throughput win for I/O-bound backends.
    Concurrency is disabled automatically when a `rate_limit_delay` is set
    (politeness wins: a throttled crawl stays serial) or when only one page is
    in flight.
    """

    config: Config
    # Backends whose `fetch` is not safe to call from multiple threads (e.g.
    # Playwright's sync API drives a single event loop) set this False to force a
    # serial walk even when concurrency is configured.
    concurrent_fetch: bool = True

    def fetch(self, url: str, **opts) -> Document:  # pragma: no cover - contract stub
        raise NotImplementedError

    def crawl(
        self, url: str, *, depth: int = 1, max_pages: int = 20, **opts
    ) -> list[Document]:
        robots = RobotsGate(self.config)
        limiter = RateLimiter(self.config.rate_limit_delay)
        seen: set[str] = {url}
        out: list[Document] = []
        frontier: list[str] = [url]
        level = 0

        while frontier and len(out) < max_pages:
            allowed = [u for u in frontier if robots.allowed(u)]
            batch = allowed[: max_pages - len(out)]  # never exceed the page cap
            docs = self._fetch_batch(batch, limiter, opts)
            out.extend(docs)
            if level >= depth:
                break
            next_frontier: list[str] = []
            for doc in docs:
                for link in doc.links:
                    if link not in seen and same_domain(link, url):
                        seen.add(link)
                        next_frontier.append(link)
            frontier = next_frontier
            level += 1
        return out[:max_pages]

    # -- batch fetch ----------------------------------------------------------
    def _fetch_batch(
        self, urls: list[str], limiter: RateLimiter, opts: dict
    ) -> list[Document]:
        """Fetch one BFS level. Concurrent when allowed, else serial+throttled.
        Results keep input order so the crawl output stays deterministic."""
        workers = max(1, self.config.crawl_concurrency)
        serial = (
            workers <= 1
            or self.config.rate_limit_delay > 0
            or len(urls) <= 1
            or not self.concurrent_fetch
        )
        if serial:
            results = []
            for u in urls:
                limiter.wait()
                results.append(self._fetch_one(u, opts))
            return results
        with ThreadPoolExecutor(max_workers=min(workers, len(urls))) as pool:
            return list(pool.map(lambda u: self._fetch_one(u, opts), urls))

    def _fetch_one(self, url: str, opts: dict) -> Document:
        """One fetch, turning any backend error into a status-0 error Document so
        a single bad page never aborts the whole crawl."""
        try:
            return self.fetch(url, **opts)
        except Exception as e:
            return Document(url=url, status=0, metadata={"error": repr(e)})
