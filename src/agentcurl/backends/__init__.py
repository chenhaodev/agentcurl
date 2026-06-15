"""Crawl backend adapters + the factory that selects one from config."""

from __future__ import annotations

import re

from ..config import Config
from .base import CrawlBackend


def _build_single(name: str, config: Config) -> CrawlBackend:
    """Build one backend by name. Heavy adapters import lazily so you only need
    the deps for the backend(s) you actually switch to."""
    if name == "static":
        from .static import StaticBackend

        return StaticBackend(config)
    if name == "browser":
        from .browser import BrowserBackend

        return BrowserBackend(config)
    if name == "crawl4ai":
        from .crawl4ai_backend import Crawl4AIBackend

        return Crawl4AIBackend(config)
    if name == "firecrawl":
        from .firecrawl_backend import FirecrawlBackend

        return FirecrawlBackend(config)
    if name == "jina":
        from .jina_backend import JinaBackend

        return JinaBackend(config)
    raise ValueError(
        f"Unknown crawl backend {name!r}. "
        "Expected one of: static, browser, crawl4ai, firecrawl, jina."
    )


def build_backend(config: Config) -> CrawlBackend:
    """Select the crawl backend(s) from CRAWL_BACKEND.

    A single name (e.g. "crawl4ai") builds that backend directly. A "+"/"," list
    (e.g. "static+browser") builds each and wraps them in a RouterBackend that
    tries them as a fallback chain (or fans out), per ROUTER_MODE.
    """
    spec = config.crawl_backend.lower()
    names = [p.strip() for p in re.split(r"[+,]", spec) if p.strip()]
    if not names:
        raise ValueError("CRAWL_BACKEND is empty; set it to e.g. 'static'.")
    if len(names) == 1:
        return _build_single(names[0], config)

    from .router import RouterBackend

    children = {name: _build_single(name, config) for name in names}
    return RouterBackend(children, mode=config.router_mode)


__all__ = ["CrawlBackend", "build_backend"]
