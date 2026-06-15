"""Shared HTTP plumbing: GET, robots.txt, same-domain link extraction, rate limit.

Backends that fetch over plain HTTP (static, jina) and the default crawl mixin
all build on these helpers so behaviour (timeouts, UA, robots, throttling) is
consistent. Pure-python + httpx; no per-backend networking quirks.
"""

from __future__ import annotations

import time
import urllib.robotparser
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from .config import Config


def http_get(url: str, config: Config) -> httpx.Response:
    """One GET with the configured UA, timeout and redirect following."""
    headers = {"User-Agent": config.user_agent}
    return httpx.get(
        url,
        headers=headers,
        timeout=config.request_timeout,
        follow_redirects=True,
    )


def same_domain(url: str, base: str) -> bool:
    """True when `url` has the exact same host (and port) as `base`, ignoring
    scheme. Intentionally strict: `www.example.com` is treated as a different
    host from `example.com`, so a crawl stays within the host it started on."""
    try:
        return urlparse(url).netloc == urlparse(base).netloc
    except Exception:
        return False


class _LinkParser(HTMLParser):
    """Collects href targets from <a> tags. Tiny + dependency-free."""

    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for key, value in attrs:
            if key == "href" and value:
                self.hrefs.append(value)


def extract_links(html: str, base_url: str, *, same_site_only: bool = True) -> list[str]:
    """Absolute, de-duplicated links from an HTML page.

    Fragments are stripped (so #section variants collapse to one URL) and only
    http(s) links are kept. With `same_site_only` (the crawl default) off-site
    links are dropped so a crawl stays within one domain.
    """
    parser = _LinkParser()
    try:
        parser.feed(html)
    except Exception:
        return []

    seen: set[str] = set()
    out: list[str] = []
    for href in parser.hrefs:
        absolute = urldefrag(urljoin(base_url, href)).url
        if not absolute.startswith(("http://", "https://")):
            continue
        if same_site_only and not same_domain(absolute, base_url):
            continue
        if absolute not in seen:
            seen.add(absolute)
            out.append(absolute)
    return out


class RobotsGate:
    """Per-crawl robots.txt cache. One parser per origin, fetched once.

    Fail-open: if robots.txt can't be fetched/parsed we allow the URL (matches
    how most polite crawlers behave) rather than silently dropping every page.
    """

    def __init__(self, config: Config):
        self.config = config
        self._cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        if not self.config.respect_robots:
            return True
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._cache:
            self._cache[origin] = self._load(origin)
        parser = self._cache[origin]
        if parser is None:
            return True  # fail-open
        return parser.can_fetch(self.config.user_agent, url)

    def _load(self, origin: str) -> urllib.robotparser.RobotFileParser | None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = httpx.get(
                f"{origin}/robots.txt",
                headers={"User-Agent": self.config.user_agent},
                timeout=self.config.request_timeout,
                follow_redirects=True,
            )
            if resp.status_code >= 400:
                return None  # no usable robots.txt -> allow everything
            rp.parse(resp.text.splitlines())
            return rp
        except Exception:
            return None


class RateLimiter:
    """Sleeps so consecutive calls are at least `delay` seconds apart. Shared
    across a crawl to be polite without each backend reimplementing throttling."""

    def __init__(self, delay: float):
        self.delay = delay
        self._last = 0.0

    def wait(self) -> None:
        if self.delay <= 0:
            return
        elapsed = time.monotonic() - self._last
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last = time.monotonic()
