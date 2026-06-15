# Contributing to agentcurl

Thanks for your interest! This is a small, focused codebase — the notes below
should get you productive quickly.

## Dev setup

```bash
git clone https://github.com/chenhaodev/agentcurl
cd agentcurl
pip install -e ".[dev]"          # core + pytest (offline development)
# pip install -e ".[all]"        # also pulls Playwright + crawl4ai
cp .env.example .env             # add DEEPSEEK_API_KEY for structured extraction
```

Python 3.10+ is required. `requirements-local-cpu.txt` documents the CPU-only
verified stack (incl. the one-time `playwright install chromium` /
`crawl4ai-setup` browser downloads) for macbook-m3 (arm64) and ubuntu.

## Running tests

```bash
python tests/test_smoke.py       # offline suite — no network, no API key, no browser
pytest -q tests/test_smoke.py    # same suite via pytest
```

The offline suite is what CI runs (Python 3.10/3.11/3.12). **Keep it green and
offline** — it must never require external network, an API key, or a browser.
(It serves fixture pages over a loopback HTTP server, which is allowed.)

Live, opt-in tests exercise the real backends and self-skip unless `RUN_LIVE=1`:

```bash
set -a && . ./.env && set +a
export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")
RUN_LIVE=1 python tests/test_live.py
```

These need network and a DeepSeek key; the browser/crawl4ai checks self-skip if
their browser isn't installed, and firecrawl skips without `FIRECRAWL_API_KEY`.

## Adding a crawl backend

The whole extension surface is the `CrawlBackend` Protocol in
`src/agentcurl/backends/base.py`:

1. Implement `fetch(url, **opts) -> Document`. Mix in `CrawlMixin` to get the
   default same-domain link-walk `crawl()` for free, or define your own `crawl`
   if the backend has native deep-crawl (see `crawl4ai`/`firecrawl`).
2. Keep to the lowest-common-denominator `Document`
   (`url, status, markdown, html, title, links, metadata`) — backend-specific
   extras go in `Document.metadata`.
3. Import the third-party lib lazily and raise a clear `ImportError` (or
   `ValueError` for a missing key) with the `pip install` line if it's missing
   (see the existing adapters).
4. Register it in `src/agentcurl/backends/__init__.py::_build_single`.
5. Add the optional dependency as an extra in `pyproject.toml`.
6. Add an offline test (factory wiring / missing-dep message) to
   `tests/test_smoke.py`, and an opt-in live test to `tests/test_live.py`.

The `RouterBackend` (`CRAWL_BACKEND="a+b"`) and `CrawlManager` work over the
Protocol, so a conforming backend needs no other changes.

## Style & conventions

- Match the surrounding code: type hints, `from __future__ import annotations`,
  small focused functions, comments that explain *why* not *what*.
- Never let an LLM/network failure crash the pipeline — degrade gracefully
  (the extractor falls back to raw markdown; the router falls through).
- Honor `robots.txt` and the rate-limit delay on any new fetching path.
- Run `python -m compileall src tests` and the offline suite before pushing.

## Pull requests

- Branch off `main`; keep commits small and focused with a clear message.
- Ensure the offline suite passes (CI will check it on 3.10–3.12).
- Note any new env vars in `.env.example` and the README config table.

By contributing you agree your contributions are licensed under the project's
[MIT License](LICENSE).
