"""Browser backend — Playwright headless Chromium for JS / dynamic pages.

When a page renders its content client-side, the static backend sees an empty
shell. This backend drives a real headless Chromium, waits for the network to go
idle, then hands the rendered HTML to trafilatura for the same clean-markdown
extraction the static backend uses. Playwright is a heavy optional dep (lazy
import + `playwright install chromium`), so it lives behind the [browser] extra.
"""

from __future__ import annotations

from .base import CrawlMixin
from .static import StaticBackend
from ..config import Config
from ..fetch_utils import extract_links
from ..types import Document


class BrowserBackend(CrawlMixin):
    name = "browser"

    def __init__(self, config: Config):
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "browser backend selected but Playwright is not installed. Run: "
                'pip install "agentcurl[browser]" && playwright install chromium'
            ) from e
        self.config = config

    def fetch(self, url: str, **opts) -> Document:
        import os

        from playwright.sync_api import sync_playwright

        # a learned recipe may carry a captured login session (cookies+localStorage)
        storage_state = opts.get("storage_state")
        if storage_state and not os.path.exists(storage_state):
            storage_state = None  # stale path -> fetch anonymously rather than crash

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.config.browser_headless)
            try:
                context = browser.new_context(
                    user_agent=self.config.user_agent, storage_state=storage_state
                )
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
                browser.close()

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
