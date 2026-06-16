"""Browser backend — Playwright headless Chromium for JS / dynamic pages.

When a page renders its content client-side, the static backend sees an empty
shell. This backend drives a real headless Chromium, waits for the network to go
idle, then hands the rendered HTML to trafilatura for the same clean-markdown
extraction the static backend uses. Playwright is a heavy optional dep (lazy
import + `playwright install chromium`), so it lives behind the [browser] extra.

One Chromium process is launched lazily and reused across every `fetch` (and so
across a whole crawl) — a fresh per-page browser launch cost tens of pages worth
of startup. Each fetch gets its own short-lived `BrowserContext` (so a recipe's
login session stays page-scoped), but the heavyweight browser stays warm until
`close()`. Playwright's sync API drives a single event loop, so the walk runs
serially (`concurrent_fetch = False`).
"""

from __future__ import annotations

import os

from .base import CrawlMixin
from .static import StaticBackend
from ..config import Config
from ..fetch_utils import extract_links
from ..types import Document


class BrowserBackend(CrawlMixin):
    name = "browser"
    concurrent_fetch = False  # Playwright sync API is single-threaded

    def __init__(self, config: Config):
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "browser backend selected but Playwright is not installed. Run: "
                'pip install "agentcurl[browser]" && playwright install chromium'
            ) from e
        self.config = config
        self._pw = None  # started Playwright driver
        self._browser = None  # launched Chromium, reused across fetches

    def _ensure_browser(self):
        """Launch Chromium once and reuse it; lazy so importing the backend (or a
        router that never reaches it) costs nothing."""
        if self._browser is None:
            from playwright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=self.config.browser_headless)
        return self._browser

    def close(self) -> None:
        """Tear down the reused browser + driver. Safe to call more than once."""
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None

    def __del__(self):  # best-effort; don't raise during GC
        try:
            self.close()
        except Exception:
            pass

    def fetch(self, url: str, **opts) -> Document:
        # a learned recipe may carry a captured login session (cookies+localStorage)
        storage_state = opts.get("storage_state")
        if storage_state and not os.path.exists(storage_state):
            storage_state = None  # stale path -> fetch anonymously rather than crash

        browser = self._ensure_browser()
        context = browser.new_context(
            user_agent=self.config.user_agent, storage_state=storage_state
        )
        try:
            page = context.new_page()
            response = page.goto(
                url,
                wait_until=self.config.browser_wait_until,
                timeout=self.config.browser_timeout * 1000,
            )
            html = page.content()
            status = response.status if response is not None else 0
            final_url = page.url
        finally:
            context.close()  # close the per-fetch context; keep the browser warm

        # reuse the static backend's trafilatura extraction on rendered HTML
        markdown, title, meta = StaticBackend._extract(html, final_url)
        return Document(
            url=final_url,
            status=status,
            markdown=markdown,
            html=html,
            title=title,
            links=extract_links(html, final_url),
            metadata={"backend": self.name, "rendered": True, **meta},
        )
