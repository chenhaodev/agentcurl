"""CrawlManager — the middleware facade tying backends + extraction + learning.

One object for the three surfaces (repo code, MCP server, SKILL) to drive:

    fetch(url)                 -> Document        one page via the active backend
    crawl(url, depth=...)      -> list[Document]  site walk (native or link-walk)
    extract(url|Document, ...) -> ExtractResult   DeepSeek -> validated JSON
    learn_login(url)           -> Recipe          capture a manual login session

The backend behind it is whatever CRAWL_BACKEND selects (a single backend, a
router chain, or "auto"); this class never imports a specific crawler.

Meta layer (the "learn + self-update" capability): when `learn` is on, every
fetch consults a per-domain Recipe (replaying captured cookies / login session /
headers) and records the outcome so the repo gets better at a site over time. In
`CRAWL_BACKEND=auto` mode it also routes each domain to the backend that has
worked best there. See recipes.py and login.py.
"""

from __future__ import annotations

from typing import Any

from .backends import CrawlBackend, build_backend, build_named
from .config import Config
from .extract import Extractor
from .fetch_utils import domain_of
from .llm import DeepSeekLLM
from .recipes import Recipe, RecipeStore
from .types import Document, ExtractResult


def _has_content(doc: Document) -> bool:
    return bool(doc.markdown.strip() or doc.html.strip())


class CrawlManager:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.from_env()
        self.llm = DeepSeekLLM(self.config)
        self.backend: CrawlBackend = build_backend(self.config)
        self.extractor = Extractor(self.llm)
        self._auto = self.config.crawl_backend.lower() == "auto"
        # autosave off: a crawl records an outcome per page, so debounce the
        # writes and flush once on close() instead of re-dumping the file 20x.
        self.recipes: RecipeStore | None = (
            RecipeStore(self.config.recipes_dir, autosave=False)
            if self.config.learn
            else None
        )
        # per-domain backend cache for auto mode (avoid rebuilding each fetch)
        self._auto_cache: dict[str, CrawlBackend] = {}

    # -- meta-layer helpers ---------------------------------------------------
    def _recipe(self, url: str) -> Recipe | None:
        return self.recipes.get(domain_of(url)) if self.recipes else None

    def _recipe_opts(self, recipe: Recipe | None) -> dict[str, Any]:
        """Turn a recipe into fetch kwargs the backends understand (only set keys
        that exist, so backends without a recipe behave exactly as before)."""
        if recipe is None:
            return {}
        opts: dict[str, Any] = {}
        if recipe.cookies:
            opts["cookies"] = recipe.cookies
        if recipe.headers:
            opts["headers"] = recipe.headers
        if recipe.storage_state:
            opts["storage_state"] = recipe.storage_state
        return opts

    def _backend_for(self, url: str, recipe: Recipe | None) -> CrawlBackend:
        """Pick the backend for this URL. In auto mode, prefer the recipe's
        learned-best backend; otherwise use the configured backend."""
        if not self._auto:
            return self.backend
        name = (recipe.best_backend if recipe else None) or "static"
        if name not in self._auto_cache:
            self._auto_cache[name] = build_named(name, self.config)
        return self._auto_cache[name]

    def _backend_name(self, backend: CrawlBackend) -> str:
        return getattr(backend, "name", "unknown")

    # -- crawl surface --------------------------------------------------------
    def fetch(self, url: str, **opts) -> Document:
        """Fetch one page as a Document. Applies any learned recipe (session /
        backend) and records the outcome so the next fetch does better."""
        recipe = self._recipe(url)
        backend = self._backend_for(url, recipe)
        merged = {**self._recipe_opts(recipe), **opts}  # explicit opts win
        doc = backend.fetch(url, **merged)
        if self.recipes is not None:
            self.recipes.record_outcome(
                domain_of(url), self._backend_name(backend), _has_content(doc)
            )
        return doc

    def crawl(
        self,
        url: str,
        *,
        depth: int | None = None,
        max_pages: int | None = None,
        **opts,
    ) -> list[Document]:
        """Crawl a site. Depth/max_pages default to config when omitted."""
        recipe = self._recipe(url)
        backend = self._backend_for(url, recipe)
        merged = {**self._recipe_opts(recipe), **opts}
        docs = backend.crawl(
            url,
            depth=self.config.crawl_depth if depth is None else depth,
            max_pages=self.config.crawl_max_pages if max_pages is None else max_pages,
            **merged,
        )
        if self.recipes is not None and docs:
            ok = any(_has_content(d) for d in docs)
            self.recipes.record_outcome(domain_of(url), self._backend_name(backend), ok)
        return docs

    # -- extraction surface ---------------------------------------------------
    def extract(self, source: str | Document, target: Any, **opts) -> ExtractResult:
        """Fetch (if given a URL) then run DeepSeek structured extraction.

        `target` is a dict/list schema or a natural-language prompt. Falls back
        to raw markdown with no DEEPSEEK_API_KEY, like agentmem's offline path.
        """
        document = self.fetch(source, **opts) if isinstance(source, str) else source
        return self.extractor.extract(document, target)

    # -- learning surface -----------------------------------------------------
    def learn_login(self, url: str, *, prompt=input) -> Recipe:
        """Watch the user log in once (headed browser) and save the session into
        this domain's recipe, so future crawls run authenticated. Requires the
        meta layer enabled (`learn`) and Playwright installed."""
        if self.recipes is None:
            raise RuntimeError(
                "learning is disabled (AGENTCURL_LEARN=0); enable it to capture a login."
            )
        from .login import record_login  # lazy: needs Playwright

        return record_login(url, self.config, self.recipes, prompt=prompt)

    # -- lifecycle ------------------------------------------------------------
    def close(self) -> None:
        """Release backend resources (pooled connections, event loops) and flush
        any debounced recipe learning to disk. Safe to call multiple times; also
        runs on context-manager exit."""
        if self.recipes is not None:
            self.recipes.flush()
        backends = [self.backend, *self._auto_cache.values()]
        for backend in backends:
            closer = getattr(backend, "close", None)
            if callable(closer):
                closer()
        self._auto_cache.clear()

    def __enter__(self) -> "CrawlManager":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
