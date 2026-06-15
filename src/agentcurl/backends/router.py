"""RouterBackend — a fallback chain or fan-out across multiple backends.

A RouterBackend *is* a CrawlBackend (same Protocol), so CrawlManager treats it
like any other single backend — it just wraps several named children. Selected
via CRAWL_BACKEND="static+browser" (a "+"/"," separated list).

Modes (ROUTER_MODE):
  fallback  try children in order, return the FIRST non-empty result. The common
            case for "just get me the page" — start cheap (static), fall through
            to heavier/remote backends (browser, firecrawl) only when needed.
  fan-out   query every child and return the single best (longest-markdown)
            result, tagging the rest in metadata for comparison.

A child raising doesn't abort the chain; its error is recorded and the next
child is tried. If at least one child raised and none produced content, the last
error is re-raised so the caller sees a real failure. If every child returned
cleanly but empty (no exceptions), the caller gets an empty result — an empty
page is a legitimate outcome, not an error.
"""

from __future__ import annotations

from .base import CrawlBackend
from ..types import Document


def _is_empty(doc: Document) -> bool:
    return not (doc.markdown.strip() or doc.html.strip())


class RouterBackend:
    def __init__(self, backends: dict[str, CrawlBackend], mode: str = "fallback"):
        if not backends:
            raise ValueError("RouterBackend needs at least one child backend")
        self.backends = backends
        self.mode = mode
        self.name = "router(" + "+".join(backends) + ")"
        self.errors: list[tuple[str, Exception]] = []

    def close(self) -> None:
        """Close any child backend that holds resources (e.g. a pooled client)."""
        for backend in self.backends.values():
            closer = getattr(backend, "close", None)
            if callable(closer):
                closer()

    def fetch(self, url: str, **opts) -> Document:
        return self._dispatch("fetch", url, **opts)

    def crawl(
        self, url: str, *, depth: int = 1, max_pages: int = 20, **opts
    ) -> list[Document]:
        result = self._dispatch(
            "crawl", url, depth=depth, max_pages=max_pages, _list=True, **opts
        )
        return result

    # -- dispatch -------------------------------------------------------------
    def _dispatch(self, method: str, url: str, *, _list: bool = False, **opts):
        candidates: list[tuple[str, object]] = []
        last_error: Exception | None = None

        for name, backend in self.backends.items():
            try:
                result = getattr(backend, method)(url, **opts)
            except Exception as e:  # resilience: try the next backend
                self.errors.append((name, e))
                last_error = e
                continue
            if self._non_empty(result, _list):
                if self.mode == "fallback":
                    return self._tag(result, name, _list)
                candidates.append((name, result))

        if self.mode == "fan-out" and candidates:
            return self._pick_best(candidates, _list)
        if last_error is not None:
            raise last_error
        # every child returned empty (no exception) -> return an empty shape
        return [] if _list else Document(url=url, status=0, metadata={"router": "empty"})

    @staticmethod
    def _non_empty(result, is_list: bool) -> bool:
        if is_list:
            return bool(result) and any(not _is_empty(d) for d in result)
        return not _is_empty(result)

    @staticmethod
    def _tag(result, name: str, is_list: bool):
        docs = result if is_list else [result]
        for d in docs:
            d.metadata = {**d.metadata, "router_backend": name}
        return result

    def _pick_best(self, candidates: list[tuple[str, object]], is_list: bool):
        def score(item) -> int:
            _, result = item
            docs = result if is_list else [result]
            return sum(len(d.markdown) for d in docs)

        name, best = max(candidates, key=score)
        return self._tag(best, name, is_list)
