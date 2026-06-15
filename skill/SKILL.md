---
name: agentcurl
description: Scrape/crawl any website and pull structured data from natural language — fetch a page as clean markdown, crawl a site, or extract JSON fields via DeepSeek. Switchable backends (static, browser, crawl4ai, firecrawl, jina). Trigger: /agentcurl
trigger: /agentcurl
---

# /agentcurl

A thin conversational layer over the **agentcurl** crawler middleware. It shells
out to `python -m agentcurl` (or the project's `mcp/server.py`), so all the real
work — backend switching, crawling, DeepSeek structured extraction — happens in
the package. The backend is chosen by the `CRAWL_BACKEND` env var
(`static` default; `browser` / `crawl4ai` / `firecrawl` / `jina`; or a
`+`-list for a fallback chain).

## Usage

```
/agentcurl <url>                              # fetch one page → clean markdown
/agentcurl crawl <url>                         # crawl the site (same-domain links)
/agentcurl <url> and pull <fields>             # extract structured JSON
/agentcurl extract <url> "<natural-language instruction>"
```

## How to run it

The package lives in this repo under `src/agentcurl/`. Run the CLI with the
repo's `src` on the path (no install needed):

1. **Fetch a page as markdown:**
   ```bash
   python -m agentcurl <url>
   ```
   If `agentcurl` isn't installed, run from the repo root with
   `PYTHONPATH=src python -m agentcurl <url>`.

2. **Crawl a site:**
   ```bash
   python -m agentcurl <url> --crawl --depth 1 --max-pages 5
   ```

3. **Extract structured data** — pick the form that matches the request:
   - Natural-language fields → `--extract`:
     ```bash
     python -m agentcurl <url> --extract "the article title, author, and a one-sentence summary" --json
     ```
   - Explicit schema → `--schema` (JSON object of field → type):
     ```bash
     python -m agentcurl <url> --schema '{"title":"str","price":"number","in_stock":"bool"}' --json
     ```

4. **Switch backend** for JS-heavy or blocked sites by setting the env var
   before the command, e.g. `CRAWL_BACKEND=browser python -m agentcurl <url>`
   (needs `playwright install chromium`) or
   `CRAWL_BACKEND=static+firecrawl ROUTER_MODE=fallback ...` for a fallback chain.

## Responding to the user

- For a plain fetch/crawl, summarize the page(s) and show the key markdown.
- For an extract, run with `--json` and present the returned JSON. If the result
  has `"raw": true`, tell the user no `DEEPSEEK_API_KEY` was set (or the LLM call
  failed) so they got raw markdown instead of structured JSON, and show a useful
  slice of it.
- If a backend import fails (e.g. Playwright not installed), relay the install
  hint from the error and suggest falling back to `CRAWL_BACKEND=static` or
  `CRAWL_BACKEND=jina` (no install).

## Install note

Copy this `skill/` directory to `~/.claude/skills/agentcurl/`. Ensure the
agentcurl package is importable (either `pip install -e .` in the repo, or invoke
with `PYTHONPATH=<repo>/src`). For extraction, set `DEEPSEEK_API_KEY` in the
environment or the repo `.env`.
