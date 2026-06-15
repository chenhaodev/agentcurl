"""Firecrawl backend — managed REST API: scrape / crawl / search.

Firecrawl is a hosted crawler that handles proxies, anti-bot and JS rendering for
you and returns clean markdown. It's the escape hatch when local backends get
blocked. We talk to the REST API directly over httpx (no SDK needed), so the
only requirement is a FIRECRAWL_API_KEY. Native crawl endpoint overrides the
link-walk mixin.

Requires: FIRECRAWL_API_KEY (get one at https://firecrawl.dev).
"""

from __future__ import annotations

import time

import httpx

from .base import CrawlMixin
from ..config import Config
from ..types import Document


class FirecrawlBackend(CrawlMixin):
    name = "firecrawl"

    def __init__(self, config: Config):
        if not config.firecrawl_api_key:
            raise ValueError(
                "firecrawl backend selected but FIRECRAWL_API_KEY is not set. "
                "Get a key at https://firecrawl.dev."
            )
        self.config = config
        self._base = config.firecrawl_base_url.rstrip("/")

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.firecrawl_api_key}",
            "Content-Type": "application/json",
        }

    def _doc_from_payload(self, url: str, data: dict) -> Document:
        meta = data.get("metadata", {}) or {}
        return Document(
            url=meta.get("sourceURL") or meta.get("url") or url,
            status=int(meta.get("statusCode", 0) or 0),
            markdown=data.get("markdown", "") or "",
            html=data.get("html", "") or "",
            title=meta.get("title", "") or "",
            links=data.get("links", []) or [],
            metadata={"backend": self.name, **{k: v for k, v in meta.items() if k != "links"}},
        )

    def fetch(self, url: str, **opts) -> Document:
        resp = httpx.post(
            f"{self._base}/v1/scrape",
            headers=self._headers,
            json={"url": url, "formats": ["markdown", "links"]},
            timeout=self.config.request_timeout,
        )
        resp.raise_for_status()
        return self._doc_from_payload(url, resp.json().get("data", {}))

    def crawl(
        self, url: str, *, depth: int = 1, max_pages: int = 20, **opts
    ) -> list[Document]:
        """Submit a crawl job, poll until complete, map each page to a Document."""
        start = httpx.post(
            f"{self._base}/v1/crawl",
            headers=self._headers,
            json={
                "url": url,
                "maxDepth": depth,
                "limit": max_pages,
                "scrapeOptions": {"formats": ["markdown", "links"]},
            },
            timeout=self.config.request_timeout,
        )
        start.raise_for_status()
        job_id = start.json().get("id")
        if not job_id:
            return []

        status_url = f"{self._base}/v1/crawl/{job_id}"
        deadline = time.monotonic() + max(self.config.request_timeout, 60) * 4
        while time.monotonic() < deadline:
            poll = httpx.get(status_url, headers=self._headers, timeout=self.config.request_timeout)
            poll.raise_for_status()
            body = poll.json()
            if body.get("status") == "completed":
                return [
                    self._doc_from_payload(url, page)
                    for page in body.get("data", [])
                ][:max_pages]
            if body.get("status") == "failed":
                raise RuntimeError(f"firecrawl crawl job failed: {body.get('error')}")
            time.sleep(2)
        raise TimeoutError("firecrawl crawl job did not complete in time")
