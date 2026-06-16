"""Crawl backend adapters + the registry that selects one from config.

Backends are looked up in a name -> factory registry instead of a hard-coded
if-chain, so a new backend is one `register_backend` call away — including
third-party ones declared via the `agentcurl.backends` entry-point group, which
are discovered automatically on first use. The built-ins register lazy factories
so you still only import the deps for the backend(s) you actually switch to.
"""

from __future__ import annotations

import importlib
import re
from typing import Callable

from ..config import Config
from .base import CrawlBackend

# name -> factory(config) -> CrawlBackend
BackendFactory = Callable[[Config], CrawlBackend]
_REGISTRY: dict[str, BackendFactory] = {}
_entry_points_loaded = False


def register_backend(name: str, factory: BackendFactory | None = None):
    """Register a backend factory under `name`. Use as a decorator on a factory
    function, or call directly with the factory. Re-registering a name overrides
    it (lets a plugin replace a built-in)."""

    def _add(f: BackendFactory) -> BackendFactory:
        _REGISTRY[name.lower()] = f
        return f

    return _add(factory) if factory is not None else _add


def _lazy(module: str, attr: str) -> BackendFactory:
    """A factory that imports `agentcurl.backends.<module>.<attr>` only when the
    backend is actually built — keeps heavy optional deps out of import time."""

    def factory(config: Config) -> CrawlBackend:
        mod = importlib.import_module(f".{module}", __package__)
        return getattr(mod, attr)(config)

    return factory


# -- built-in backends --------------------------------------------------------
register_backend("static", _lazy("static", "StaticBackend"))
register_backend("browser", _lazy("browser", "BrowserBackend"))
register_backend("crawl4ai", _lazy("crawl4ai_backend", "Crawl4AIBackend"))
register_backend("firecrawl", _lazy("firecrawl_backend", "FirecrawlBackend"))
register_backend("jina", _lazy("jina_backend", "JinaBackend"))


def _load_entry_point_backends() -> None:
    """Discover third-party backends declared under the `agentcurl.backends`
    entry-point group, once. Best-effort: a broken plugin never breaks the
    built-ins. A built-in name is not overridden by a same-named plugin."""
    global _entry_points_loaded
    if _entry_points_loaded:
        return
    _entry_points_loaded = True
    try:
        from importlib.metadata import entry_points

        eps = entry_points()
        group = (
            eps.select(group="agentcurl.backends")
            if hasattr(eps, "select")
            else eps.get("agentcurl.backends", [])  # py<3.10 mapping API
        )
        for ep in group:
            if ep.name.lower() not in _REGISTRY:
                register_backend(ep.name, lambda config, _ep=ep: _ep.load()(config))
    except Exception:
        pass  # discovery is optional; the built-ins always work


def _build_single(name: str, config: Config) -> CrawlBackend:
    """Build one backend by name from the registry (discovering plugins first)."""
    _load_entry_point_backends()
    factory = _REGISTRY.get(name.lower())
    if factory is None:
        known = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"Unknown crawl backend {name!r}. Expected one of: {known}.")
    return factory(config)


def build_named(name: str, config: Config) -> CrawlBackend:
    """Build one backend by name (public alias of the single-backend factory),
    used by CrawlManager's per-domain `auto` selection."""
    return _build_single(name, config)


def build_backend(config: Config) -> CrawlBackend:
    """Select the crawl backend(s) from CRAWL_BACKEND.

    A single name (e.g. "crawl4ai") builds that backend directly. A "+"/"," list
    (e.g. "static+browser") builds each and wraps them in a RouterBackend that
    tries them as a fallback chain (or fans out), per ROUTER_MODE. The special
    value "auto" defers per-domain backend choice to CrawlManager (which uses
    learned recipes), defaulting to static until something better is learned.
    """
    spec = config.crawl_backend.lower()
    if spec == "auto":
        return _build_single("static", config)  # sensible default; manager may swap per domain
    names = [p.strip() for p in re.split(r"[+,]", spec) if p.strip()]
    if not names:
        raise ValueError("CRAWL_BACKEND is empty; set it to e.g. 'static'.")
    if len(names) == 1:
        return _build_single(names[0], config)

    from .router import RouterBackend

    children = {name: _build_single(name, config) for name in names}
    return RouterBackend(children, mode=config.router_mode)


__all__ = ["CrawlBackend", "build_backend", "build_named", "register_backend"]
