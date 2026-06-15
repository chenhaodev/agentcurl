"""Offline smoke tests for agentcurl. Run: python tests/test_smoke.py

No external network, no API key, no browser. A tiny loopback HTTP server serves
the fixture pages so the REAL static backend (httpx + trafilatura) fetch/crawl
paths are exercised end-to-end; the rest is in-process (link parsing, router
fallback/fan-out, the factory, and the extractor's offline raw fallback). Plain
asserts so it runs without pytest, but `pytest tests/` also discovers the
test_* functions.
"""

from __future__ import annotations

import functools
import http.server
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agentcurl import Config, CrawlManager, Document  # noqa: E402
from agentcurl.backends import build_backend  # noqa: E402
from agentcurl.backends.base import CrawlBackend, CrawlMixin  # noqa: E402
from agentcurl.backends.router import RouterBackend  # noqa: E402
from agentcurl.backends.static import StaticBackend  # noqa: E402
from agentcurl.extract import Extractor  # noqa: E402
from agentcurl.fetch_utils import extract_links  # noqa: E402
from agentcurl.llm import DeepSeekLLM  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _cfg(**kw) -> Config:
    base = dict(
        crawl_backend="static",
        deepseek_api_key="",  # force the offline raw-markdown extraction path
        respect_robots=False,  # the loopback server has no robots.txt
        rate_limit_delay=0,
    )
    base.update(kw)
    return Config(**base)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep test output clean
        pass


class _FixtureServer:
    """Serves tests/fixtures over loopback so static.fetch hits a real socket."""

    def __enter__(self) -> str:
        handler = functools.partial(_QuietHandler, directory=FIXTURES)
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        port = self.httpd.server_address[1]
        return f"http://127.0.0.1:{port}"

    def __exit__(self, *exc) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


# -- link parsing (pure, no network) -----------------------------------------
def test_extract_links_absolute_same_site_and_dedup():
    html = (
        '<a href="/a.html">a</a><a href="/a.html#frag">dup</a>'
        '<a href="https://other.example/x">off</a><a href="mailto:x@y.z">mail</a>'
    )
    links = extract_links(html, "http://site.test/dir/page.html")
    assert "http://site.test/a.html" in links
    assert all("other.example" not in link for link in links), links  # off-site dropped
    assert all(not link.startswith("mailto") for link in links)  # non-http dropped
    assert len(links) == len(set(links)), "fragments should collapse to one URL"
    print("ok  extract_links: absolute, same-site, deduped, http-only")


# -- static backend over loopback (real fetch) --------------------------------
def test_static_fetch_real_socket():
    with _FixtureServer() as base:
        backend = StaticBackend(_cfg())
        doc = backend.fetch(f"{base}/article.html")
    assert doc.status == 200, doc.status
    assert "Tides of Tomorrow" in doc.title, doc.title
    assert "coastal" in doc.markdown.lower(), doc.markdown[:200]
    assert doc.metadata.get("author") == "Jane Rivers", doc.metadata
    # same-site links kept, off-site dropped
    assert any(link.endswith("/page2.html") for link in doc.links), doc.links
    assert all("external.example.org" not in link for link in doc.links)
    assert isinstance(backend, CrawlBackend)  # satisfies the Protocol
    print("ok  static.fetch: real httpx+trafilatura -> markdown/title/links")


def test_static_crawl_walks_same_domain():
    with _FixtureServer() as base:
        cm = CrawlManager(_cfg())
        docs = cm.crawl(f"{base}/article.html", depth=1, max_pages=10)
    urls = {d.url for d in docs}
    assert any(u.endswith("/article.html") for u in urls), urls
    assert any(u.endswith("/page2.html") for u in urls), urls  # followed a link
    assert len(docs) <= 10
    print(f"ok  static.crawl: walked {len(docs)} same-domain pages")


def test_crawl_respects_max_pages():
    with _FixtureServer() as base:
        cm = CrawlManager(_cfg())
        docs = cm.crawl(f"{base}/article.html", depth=3, max_pages=1)
    assert len(docs) == 1, f"max_pages ignored: {len(docs)}"
    print("ok  crawl honors max_pages cap")


# -- crawl mixin via a fake fetch (no network) --------------------------------
class _FakeBackend(CrawlMixin):
    name = "fake"

    def __init__(self, pages: dict[str, Document]):
        self.config = _cfg()
        self.pages = pages

    def fetch(self, url: str, **opts) -> Document:
        return self.pages[url]


def test_mixin_crawl_dedups_and_bounds_depth():
    pages = {
        "http://x.test/": Document(url="http://x.test/", markdown="root", links=["http://x.test/a", "http://x.test/b"]),
        "http://x.test/a": Document(url="http://x.test/a", markdown="a", links=["http://x.test/"]),  # back-link
        "http://x.test/b": Document(url="http://x.test/b", markdown="b", links=["http://x.test/c"]),
        "http://x.test/c": Document(url="http://x.test/c", markdown="c", links=[]),
    }
    docs = _FakeBackend(pages).crawl("http://x.test/", depth=1, max_pages=20)
    urls = [d.url for d in docs]
    assert urls.count("http://x.test/") == 1, "root visited twice (dedup failed)"
    assert "http://x.test/c" not in urls, "depth-2 page should not be reached at depth=1"
    print("ok  mixin crawl: dedups visited URLs and bounds by depth")


# -- router fallback / fan-out ------------------------------------------------
class _CannedBackend:
    def __init__(self, name: str, md: str, *, boom: bool = False):
        self.name = name
        self.md = md
        self.boom = boom

    def fetch(self, url: str, **opts) -> Document:
        if self.boom:
            raise RuntimeError(f"{self.name} down")
        return Document(url=url, markdown=self.md, metadata={"backend": self.name})

    def crawl(self, url, *, depth=1, max_pages=20, **opts):
        return [self.fetch(url)]


def test_router_fallback_skips_failures_and_empties():
    router = RouterBackend(
        {
            "boom": _CannedBackend("boom", "", boom=True),
            "empty": _CannedBackend("empty", "   "),
            "good": _CannedBackend("good", "real content"),
        },
        mode="fallback",
    )
    doc = router.fetch("http://x.test")
    assert doc.markdown == "real content", doc
    assert doc.metadata["router_backend"] == "good", doc.metadata
    assert ("boom" in dict(router.errors)) or any(n == "boom" for n, _ in router.errors)
    print("ok  router fallback: skips error + empty, returns first real result")


def test_router_fanout_picks_longest_markdown():
    router = RouterBackend(
        {"short": _CannedBackend("short", "abc"), "long": _CannedBackend("long", "a much longer body")},
        mode="fan-out",
    )
    doc = router.fetch("http://x.test")
    assert doc.metadata["router_backend"] == "long", doc.metadata
    print("ok  router fan-out: picks the richest (longest-markdown) result")


def test_router_all_fail_reraises():
    router = RouterBackend({"a": _CannedBackend("a", "", boom=True)}, mode="fallback")
    try:
        router.fetch("http://x.test")
        assert False, "expected the child error to propagate"
    except RuntimeError as e:
        assert "down" in str(e)
    print("ok  router re-raises when every child fails")


# -- factory ------------------------------------------------------------------
def test_factory_single_vs_router_and_errors():
    assert isinstance(build_backend(_cfg(crawl_backend="static")), StaticBackend)
    router = build_backend(_cfg(crawl_backend="static+jina"))
    assert isinstance(router, RouterBackend)
    assert set(router.backends) == {"static", "jina"}
    try:
        build_backend(_cfg(crawl_backend="nope"))
        assert False, "expected ValueError for unknown backend"
    except ValueError as e:
        assert "static" in str(e)  # error lists the known backends
    print("ok  factory: single vs router list, helpful unknown-backend error")


# -- extractor offline fallback -----------------------------------------------
def test_extractor_offline_raw_fallback():
    ext = Extractor(DeepSeekLLM(_cfg()))  # no key -> raw path
    doc = Document(url="http://x.test", markdown="# Title\nbody text", title="Title")
    res = ext.extract(doc, {"title": "str", "summary": "str"})
    assert res.raw is True
    assert res.data == "# Title\nbody text"
    assert res.fields == ["title", "summary"]
    print("ok  extractor: offline/no-key falls back to raw markdown")


def test_manager_extract_from_document_offline():
    cm = CrawlManager(_cfg())
    doc = Document(url="http://x.test", markdown="hello world")
    res = cm.extract(doc, "the greeting")
    assert res.raw and res.data == "hello world"
    print("ok  manager.extract accepts a Document and runs offline")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    main()
