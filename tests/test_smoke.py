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
import tempfile
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agentcurl import Config, CrawlManager, Document  # noqa: E402
from agentcurl.backends import build_backend  # noqa: E402
from agentcurl.backends.base import CrawlBackend, CrawlMixin  # noqa: E402
from agentcurl.backends.router import RouterBackend  # noqa: E402
from agentcurl.backends.static import StaticBackend  # noqa: E402
from agentcurl.extract import Extractor, parse_target  # noqa: E402
from agentcurl.fetch_utils import decode_html, extract_links  # noqa: E402
from agentcurl.llm import DeepSeekLLM  # noqa: E402
from agentcurl.recipes import Recipe, RecipeStore  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _cfg(**kw) -> Config:
    base = dict(
        crawl_backend="static",
        deepseek_api_key="",  # force the offline raw-markdown extraction path
        respect_robots=False,  # the loopback server has no robots.txt
        rate_limit_delay=0,
        learn=False,  # keep tests hermetic; recipe tests opt in with a temp dir
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


# -- charset detection (pure, no network) -------------------------------------
def test_decode_html_sniffs_meta_charset():
    """A GBK page with no HTTP charset header must decode via its <meta charset>,
    not silently mojibake as UTF-8 (regression: legacy Chinese sites like
    xywy.com)."""
    import httpx

    title = "寻医问药网"
    html = f'<html><head><meta charset="gbk"><title>{title}</title></head></html>'
    raw = html.encode("gbk")
    # no charset in Content-Type -> httpx would assume utf-8 and corrupt it
    resp = httpx.Response(200, content=raw, headers={"content-type": "text/html"})
    assert resp.charset_encoding is None
    assert title in decode_html(resp), "meta charset not honored"
    # header charset still wins when present
    resp2 = httpx.Response(
        200, content="café".encode("utf-8"),
        headers={"content-type": "text/html; charset=utf-8"},
    )
    assert decode_html(resp2) == "café"
    print("ok  decode_html: sniffs <meta charset>, respects header charset")


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


def test_static_pooled_client_reused_and_closed():
    """The static backend reuses one pooled httpx.Client across fetches and the
    manager's close()/context-manager releases it."""
    with _FixtureServer() as base:
        with CrawlManager(_cfg()) as cm:
            backend = cm.backend
            cm.fetch(f"{base}/article.html")
            client_after_first = backend._client
            cm.fetch(f"{base}/page2.html")
            assert backend._client is client_after_first, "client not reused across fetches"
            assert client_after_first is not None and not client_after_first.is_closed
        # context-manager exit closed it
        assert backend._client is None, "manager exit did not close the pooled client"
    print("ok  static backend reuses one pooled client and closes on exit")


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


def test_parse_target_json_vs_prompt():
    assert parse_target('{"title":"str"}') == {"title": "str"}  # dict schema
    assert parse_target('["title","price"]') == ["title", "price"]  # list schema
    assert parse_target("the article title and author") == "the article title and author"
    assert parse_target("not json {oops") == "not json {oops"  # invalid JSON -> prompt
    assert parse_target("42") == "42"  # bare scalar JSON is a prompt, not a schema
    print("ok  parse_target: dict/list schema vs natural-language prompt")


def test_extractor_list_schema_fields():
    """A list schema must surface its field names (regression: lists were
    silently downgraded to a prompt with empty fields)."""
    ext = Extractor(DeepSeekLLM(_cfg()))  # no key -> raw path, but fields still set
    doc = Document(url="http://x.test", markdown="body")
    res = ext.extract(doc, ["title", "price"])
    assert res.fields == ["title", "price"], res.fields
    print("ok  extractor: list schema surfaces its field names")


def test_manager_extract_from_document_offline():
    cm = CrawlManager(_cfg())
    doc = Document(url="http://x.test", markdown="hello world")
    res = cm.extract(doc, "the greeting")
    assert res.raw and res.data == "hello world"
    print("ok  manager.extract accepts a Document and runs offline")


# -- meta layer: recipe store + learning --------------------------------------
def test_recipe_store_roundtrip_and_domain_keying():
    with tempfile.TemporaryDirectory() as d:
        store = RecipeStore(d)
        assert store.get("example.com") is None  # unlearned -> None
        r = Recipe(domain="example.com", cookies={"sid": "abc"}, headers={"X-Auth": "t"})
        store.save(r)
        got = store.get("example.com")
        assert got is not None and got.cookies == {"sid": "abc"} and got.headers == {"X-Auth": "t"}
        # weird domain chars don't escape the dir / collide
        store.save(Recipe(domain="host:8080/../x"))
        assert store.get("host:8080/../x") is not None
        # recipes hold session cookies -> owner-only file + dir perms
        import stat
        mode = stat.S_IMODE(os.stat(store._path("example.com")).st_mode)
        assert mode == 0o600, oct(mode)
        assert stat.S_IMODE(os.stat(d).st_mode) == 0o700, oct(os.stat(d).st_mode)
    print("ok  recipe store: roundtrip, safe domain keying, owner-only perms")


def test_record_outcome_learns_best_backend():
    with tempfile.TemporaryDirectory() as d:
        store = RecipeStore(d)
        # static keeps failing here, jina keeps working -> jina becomes best
        store.record_outcome("site.test", "static", ok=False)
        store.record_outcome("site.test", "static", ok=False)
        store.record_outcome("site.test", "jina", ok=True)
        r = store.record_outcome("site.test", "jina", ok=True)
        assert r.best_backend == "jina", r.best_backend
        assert r.successes["jina"] == 2 and r.attempts["static"] == 2
        # a backend that never succeeds is never chosen as best
        store2 = RecipeStore(d)
        only_fail = store2.record_outcome("fail.test", "static", ok=False)
        assert only_fail.best_backend is None
    print("ok  record_outcome: learns the best-performing backend per domain")


def test_manager_replays_recipe_cookies():
    """A learned recipe's cookies must be sent on the next fetch (the core of
    'log in once, reuse the session next time') — verified over loopback."""
    class _CookieEcho(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = f"<html><body>cookie={self.headers.get('Cookie', '')}</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode())

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _CookieEcho)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        port = httpd.server_address[1]
        domain = f"127.0.0.1:{port}"
        with tempfile.TemporaryDirectory() as d:
            store = RecipeStore(d)
            store.save(Recipe(domain=domain, cookies={"session": "xyz123"}))
            cfg = _cfg(learn=True, recipes_dir=d)
            with CrawlManager(cfg) as cm:
                doc = cm.fetch(f"http://{domain}/")
            assert "session=xyz123" in doc.html, doc.html
            # outcome got recorded for this domain
            assert store.get(domain).attempts.get("static", 0) >= 1
    finally:
        httpd.shutdown()
        httpd.server_close()
    print("ok  manager replays learned cookies + records the outcome")


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    main()
