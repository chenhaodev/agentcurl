"""Static backend — httpx GET + trafilatura extraction. The zero-dep default.

Best lightweight local extractor: no browser, no GPU, milliseconds per page.
Fetches raw HTML over httpx, then trafilatura turns the article body into clean
markdown and pulls the title. Links come from our own dependency-free parser so
the crawl mixin can walk the site. This is the clearest reference implementation
of the CrawlBackend contract — every other adapter mirrors its shape.
"""

from __future__ import annotations

import httpx

from .base import CrawlMixin
from ..config import Config
from ..fetch_utils import build_client, extract_links, http_get
from ..types import Document


class StaticBackend(CrawlMixin):
    name = "static"

    def __init__(self, config: Config):
        self.config = config
        self._client: httpx.Client | None = None  # lazy pooled connection

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = build_client(self.config)
        return self._client

    def close(self) -> None:
        """Release the pooled connection. Safe to call more than once."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __del__(self):  # best-effort; don't raise during GC
        try:
            self.close()
        except Exception:
            pass

    def fetch(self, url: str, **opts) -> Document:
        resp = http_get(url, self.config, client=self.client)
        html = resp.text
        markdown, title, meta = self._extract(html, url)
        return Document(
            url=str(resp.url),
            status=resp.status_code,
            markdown=markdown,
            html=html,
            title=title,
            links=extract_links(html, str(resp.url)),
            metadata={"backend": self.name, **meta},
        )

    @staticmethod
    def _extract(html: str, url: str) -> tuple[str, str, dict]:
        """trafilatura -> (markdown, title, metadata). Degrades gracefully when
        trafilatura finds no article body (e.g. a link hub) by returning empty
        markdown rather than raising — the caller still gets html + links."""
        try:
            import trafilatura
        except ImportError as e:  # pragma: no cover - trafilatura is a core dep
            raise ImportError(
                "static backend needs trafilatura. Run: pip install trafilatura"
            ) from e

        title = ""
        meta: dict = {}
        try:
            extracted = trafilatura.extract(
                html,
                url=url,
                output_format="markdown",
                include_links=True,
                with_metadata=False,
            )
        except Exception:
            extracted = None
        try:
            md = trafilatura.metadata.extract_metadata(html)
            if md is not None:
                title = md.title or ""
                meta = {
                    k: v
                    for k, v in {
                        "author": md.author,
                        "date": md.date,
                        "description": md.description,
                        "sitename": md.sitename,
                    }.items()
                    if v
                }
        except Exception:
            pass
        return extracted or "", title, meta
