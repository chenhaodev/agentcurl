"""Opt-in LIVE integration tests — real sites + DeepSeek + remote backends.

SKIPPED unless RUN_LIVE=1, because they need network, a DeepSeek key, and (for
some) optional backend deps / API keys. They encode the setups verified by hand
so the heavier adapters don't silently rot.

Run:
    set -a && . ./.env && set +a
    export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")
    RUN_LIVE=1 python tests/test_live.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agentcurl import Config, CrawlManager  # noqa: E402

LIVE = os.getenv("RUN_LIVE") == "1"


def _skip(name: str, *, need_key: str | None = None) -> bool:
    if not LIVE:
        print(f"skip {name} (set RUN_LIVE=1 to run)")
        return True
    if need_key and not os.getenv(need_key):
        print(f"skip {name} (no {need_key})")
        return True
    return False


def _cfg(backend: str) -> Config:
    cfg = Config.from_env()
    cfg.crawl_backend = backend
    return cfg


def _missing_browser(e: Exception) -> bool:
    """True when a browser-driven backend failed only because its browser binary
    or package isn't installed — a skip, not a real failure."""
    msg = str(e).lower()
    return isinstance(e, ImportError) or any(
        s in msg for s in ("executable doesn't exist", "playwright install", "browser")
    )


def test_static_live():
    """Real httpx + trafilatura against example.com."""
    if _skip("static"):
        return
    cm = CrawlManager(_cfg("static"))
    doc = cm.fetch("https://example.com")
    assert doc.status == 200, doc.status
    assert "example" in doc.markdown.lower(), doc.markdown[:200]
    print("ok  static live: fetched example.com")


def test_extract_live():
    """DeepSeek structured extraction on a real page -> JSON dict."""
    if _skip("extract", need_key="DEEPSEEK_API_KEY"):
        return
    cm = CrawlManager(_cfg("static"))
    res = cm.extract("https://example.com", {"title": "str", "summary": "str"})
    assert not res.raw, "expected a real LLM extraction, got raw fallback"
    assert isinstance(res.data, dict) and "title" in res.data, res.data
    print(f"ok  extract live: {res.data}")


def test_jina_live():
    """r.jina.ai remote reader -> markdown (no install, key optional)."""
    if _skip("jina"):
        return
    cm = CrawlManager(_cfg("jina"))
    doc = cm.fetch("https://example.com")
    assert doc.markdown.strip(), "jina returned empty markdown"
    print("ok  jina live: remote reader returned markdown")


def test_browser_live():
    """Playwright headless Chromium (needs: playwright install chromium)."""
    if _skip("browser"):
        return
    try:
        cm = CrawlManager(_cfg("browser"))
        doc = cm.fetch("https://example.com")
    except Exception as e:
        if _missing_browser(e):
            print(f"skip browser (not installed: run `playwright install chromium`)")
            return
        raise
    assert doc.status in (200, 0) and doc.markdown.strip(), doc
    print("ok  browser live: rendered example.com")


def test_crawl4ai_live():
    if _skip("crawl4ai"):
        return
    try:
        cm = CrawlManager(_cfg("crawl4ai"))
        doc = cm.fetch("https://example.com")
    except Exception as e:
        if _missing_browser(e):
            print(f"skip crawl4ai (not installed: run `pip install crawl4ai && crawl4ai-setup`)")
            return
        raise
    assert doc.markdown.strip(), "crawl4ai returned empty markdown"
    print("ok  crawl4ai live: fit-markdown returned")


def test_firecrawl_live():
    if _skip("firecrawl", need_key="FIRECRAWL_API_KEY"):
        return
    cm = CrawlManager(_cfg("firecrawl"))
    doc = cm.fetch("https://example.com")
    assert doc.markdown.strip(), "firecrawl returned empty markdown"
    print("ok  firecrawl live: scrape returned markdown")


def main():
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = []
    for name, t in tests:
        try:
            t()
        except Exception as e:  # isolate: one live failure shouldn't hide the rest
            failures.append(name)
            print(f"FAIL {name}: {e!r}")
    print(f"\n{len(tests)} checks run, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
