"""Shared data types used across every crawl backend.

`Document` is the lowest-common-denominator shape every backend returns from
`fetch`/`crawl`. Backend-specific superpowers (Firecrawl screenshots, crawl4ai
fit-markdown scores, Playwright timing) ride in `metadata` so the common
interface stays portable. `ExtractResult` wraps the LLM structured-extraction
output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    """One fetched page, normalized across every backend."""

    url: str
    status: int = 0  # HTTP status (0 when a backend doesn't expose one)
    markdown: str = ""  # primary content as markdown / clean text
    html: str = ""  # raw HTML when the backend provides it
    title: str = ""
    links: list[str] = field(default_factory=list)  # absolute, same-page links
    metadata: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:  # nicer demo output
        chars = len(self.markdown)
        return (
            f"Document(url={self.url!r}, status={self.status}, "
            f"title={self.title!r}, markdown={chars} chars, "
            f"links={len(self.links)})"
        )


@dataclass
class ExtractResult:
    """Structured data pulled from a page by the LLM extractor."""

    url: str
    data: Any  # validated JSON (dict/list) or, on the offline fallback, raw markdown
    fields: list[str] = field(default_factory=list)  # schema keys requested, if any
    raw: bool = False  # True when this is the no-key raw-markdown fallback
    metadata: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        kind = "raw-markdown" if self.raw else "json"
        return f"ExtractResult(url={self.url!r}, kind={kind}, fields={self.fields})"
