"""Configuration loaded from environment / .env.

Same shape as agentmem's Config: a frozen-ish dataclass with a `from_env`
classmethod and optional python-dotenv loading. Every tunable is an env var so
the package, the MCP server, and the SKILL all configure identically.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()  # populate os.environ from .env if present
except Exception:  # python-dotenv optional at import time
    pass


@dataclass
class Config:
    # --- DeepSeek (OpenAI-compatible) — powers structured extraction ---
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_timeout: int = 60
    deepseek_max_retries: int = 3

    # --- backend selection ---
    # single ("crawl4ai") or a "+"/"," list ("static+browser") for a router chain
    crawl_backend: str = "static"  # static | browser | crawl4ai | firecrawl | jina | a+b
    router_mode: str = "fallback"  # fallback (first non-empty wins) | fan-out

    # --- crawl limits (shared across backends) ---
    crawl_depth: int = 1  # link-following depth for crawl()
    crawl_max_pages: int = 20  # hard cap on pages fetched per crawl()
    request_timeout: int = 30  # per-request HTTP timeout (seconds)
    rate_limit_delay: float = 0.0  # seconds to sleep between same-domain fetches
    user_agent: str = "agentcurl/0.1 (+https://github.com/chenhaodev/agentcurl)"
    respect_robots: bool = True  # honor robots.txt on the static link-walk crawl

    # --- browser backend (Playwright) ---
    browser_headless: bool = True
    browser_wait_until: str = "networkidle"  # load | domcontentloaded | networkidle
    browser_timeout: int = 30  # page navigation timeout (seconds)

    # --- crawl4ai backend ---
    crawl4ai_fit_markdown: bool = True  # use pruned "fit" markdown when available

    # --- firecrawl backend (managed REST API) ---
    firecrawl_api_key: str = ""
    firecrawl_base_url: str = "https://api.firecrawl.dev"

    # --- jina backend (r.jina.ai reader) ---
    jina_api_key: str = ""  # optional: higher rate limits
    jina_base_url: str = "https://r.jina.ai"

    # --- meta-learning layer (per-domain recipes) ---
    learn: bool = True  # record per-domain outcomes + auto-apply learned recipes
    recipes_dir: str = ".agentcurl/recipes"  # where learned recipes are stored

    @classmethod
    def from_env(cls) -> "Config":
        def _flag(name: str, default: str = "") -> bool:
            return os.getenv(name, default).lower() in ("1", "true", "yes")

        return cls(
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            deepseek_base_url=os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
            deepseek_timeout=int(os.getenv("DEEPSEEK_TIMEOUT", "60")),
            deepseek_max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "3")),
            crawl_backend=os.getenv("CRAWL_BACKEND", "static"),
            router_mode=os.getenv("ROUTER_MODE", "fallback"),
            crawl_depth=int(os.getenv("CRAWL_DEPTH", "1")),
            crawl_max_pages=int(os.getenv("CRAWL_MAX_PAGES", "20")),
            request_timeout=int(os.getenv("REQUEST_TIMEOUT", "30")),
            rate_limit_delay=float(os.getenv("RATE_LIMIT_DELAY", "0")),
            user_agent=os.getenv(
                "CRAWL_USER_AGENT",
                "agentcurl/0.1 (+https://github.com/chenhaodev/agentcurl)",
            ),
            respect_robots=_flag("RESPECT_ROBOTS", "1"),
            browser_headless=_flag("BROWSER_HEADLESS", "1"),
            browser_wait_until=os.getenv("BROWSER_WAIT_UNTIL", "networkidle"),
            browser_timeout=int(os.getenv("BROWSER_TIMEOUT", "30")),
            crawl4ai_fit_markdown=_flag("CRAWL4AI_FIT_MARKDOWN", "1"),
            firecrawl_api_key=os.getenv("FIRECRAWL_API_KEY", ""),
            firecrawl_base_url=os.getenv("FIRECRAWL_API_BASE", "https://api.firecrawl.dev"),
            jina_api_key=os.getenv("JINA_API_KEY", ""),
            jina_base_url=os.getenv("JINA_API_BASE", "https://r.jina.ai"),
            learn=_flag("AGENTCURL_LEARN", "1"),
            recipes_dir=os.getenv("AGENTCURL_RECIPES_DIR", ".agentcurl/recipes"),
        )
