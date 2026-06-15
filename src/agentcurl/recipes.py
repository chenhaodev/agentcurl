"""The meta-learning layer: per-domain "recipes" the repo learns and reuses.

The idea: agentcurl shouldn't make you re-solve a site every time. After it has
seen a domain once it remembers what worked — which backend produced content,
and any session captured from a manual login (cookies + browser storage) — and
replays that automatically next time, so the next crawl just works.

A `Recipe` is the learned knowledge for one domain:
  - `best_backend`  the backend that has most reliably returned content here
                    (learned from outcomes; used by CRAWL_BACKEND=auto)
  - `cookies`       name→value sent as a Cookie header by static/jina
  - `storage_state` path to a Playwright storage_state file (cookies + localStorage)
                    captured from a manual login; replayed by the browser backend
  - `headers`       extra request headers (e.g. an auth token)
  - `attempts` / `successes`  per-backend tallies behind `best_backend`

`RecipeStore` persists one JSON file per domain under a base dir. Everything is
plain JSON and degrades to "no recipe" if a file is missing or unreadable, so a
fresh checkout simply has nothing learned yet.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any


def _safe_name(domain: str) -> str:
    """Filesystem-safe filename for a domain (host[:port])."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", domain) or "_"


@dataclass
class Recipe:
    domain: str
    best_backend: str | None = None
    cookies: dict[str, str] = field(default_factory=dict)
    storage_state: str | None = None  # path to a Playwright storage_state json
    headers: dict[str, str] = field(default_factory=dict)
    attempts: dict[str, int] = field(default_factory=dict)
    successes: dict[str, int] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Recipe":
        known = {f for f in cls.__dataclass_fields__}  # ignore unknown/legacy keys
        return cls(**{k: v for k, v in data.items() if k in known})

    def record(self, backend: str, ok: bool) -> None:
        """Tally one outcome and recompute `best_backend` (highest success rate,
        ties broken by attempt count so a well-proven backend wins)."""
        self.attempts[backend] = self.attempts.get(backend, 0) + 1
        if ok:
            self.successes[backend] = self.successes.get(backend, 0) + 1
        ranked = sorted(
            self.attempts,
            key=lambda b: (
                self.successes.get(b, 0) / self.attempts[b],
                self.attempts[b],
            ),
            reverse=True,
        )
        # only adopt a best_backend that has actually succeeded at least once
        winner = next((b for b in ranked if self.successes.get(b, 0) > 0), None)
        if winner is not None:
            self.best_backend = winner


class RecipeStore:
    """JSON-file-per-domain recipe persistence. Missing/corrupt files read as
    "no recipe" so learning is always best-effort and never fatal."""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    def _path(self, domain: str) -> str:
        return os.path.join(self.base_dir, f"{_safe_name(domain)}.json")

    def get(self, domain: str) -> Recipe | None:
        path = self._path(domain)
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                return Recipe.from_dict(json.load(f))
        except Exception:
            return None  # unreadable -> treat as unlearned

    def save(self, recipe: Recipe) -> None:
        # recipes can hold session cookies, so keep the dir + files owner-only.
        os.makedirs(self.base_dir, mode=0o700, exist_ok=True)
        try:
            os.chmod(self.base_dir, 0o700)  # tighten even if it pre-existed
        except OSError:
            pass
        path = self._path(recipe.domain)
        tmp = f"{path}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(recipe.to_dict(), f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)  # atomic; preserves the 0o600 mode

    def record_outcome(self, domain: str, backend: str, ok: bool) -> Recipe:
        """Update (or create) a domain's recipe with one crawl outcome."""
        recipe = self.get(domain) or Recipe(domain=domain)
        recipe.record(backend, ok)
        self.save(recipe)
        return recipe
