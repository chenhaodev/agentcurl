# agentcurl — a switchable web-crawler middleware

[![CI](https://github.com/chenhaodev/agentcurl/actions/workflows/ci.yml/badge.svg)](https://github.com/chenhaodev/agentcurl/actions/workflows/ci.yml)

One interface over five pluggable crawl backends, switched by a single env var,
with **structured LLM extraction** (DeepSeek-V4-Flash) layered on top. Drive it
from **repo code**, an **MCP server**, or a **Claude Code SKILL** — all three are
thin wrappers over the same `CrawlManager`.

`5 backends` · `zero-dep default` · `1 env var to switch` · `URL → JSON` · `3 surfaces` · `CPU-only`

Sibling of [agentmem](https://github.com/chenhaodev/agentmem), built on the same
shape: *one common interface, many pluggable backends, env-switched.*

```python
from agentcurl import CrawlManager

with CrawlManager() as cm:                           # backend chosen by CRAWL_BACKEND
    doc = cm.fetch("https://example.com")            # -> Document (markdown + links + meta)
    docs = cm.crawl("https://example.com", depth=1)  # -> list[Document]
    data = cm.extract(doc, {"title": "str", "price": "number"})  # -> ExtractResult (JSON)
```

## In one minute (no scraping background needed)

**The problem.** Scraping a site is never one job. Some pages are plain HTML
(fast to parse); some render content with JavaScript (need a real browser); some
block you (need a managed proxy service); and once you have the page you usually
want *structured data*, not a wall of text. People end up gluing together
trafilatura + Playwright + an API client + an LLM call, with bespoke code each
time.

**What this does.** It puts all of those behind **one interface** —
`fetch` / `crawl` / `extract` — and lets you pick the engine with a single env
var (`CRAWL_BACKEND=static` → `browser` → `crawl4ai` → `firecrawl` → `jina`, or a
`+`-list that falls back across them). The default needs zero extra installs;
heavier engines are opt-in. `extract` then turns any page into JSON via DeepSeek
— and falls back to raw markdown when there's no API key, so nothing ever
crashes offline.

> **In a sentence:** stop rewriting the fetch-render-extract glue per site —
> point one `CrawlManager` at a URL and switch engines with an env var.

## See it work

Pull structured JSON straight from a page on the command line:

```bash
$ python -m agentcurl https://en.wikipedia.org/wiki/Web_scraping \
    --schema '{"title":"str","first_sentence":"str","key_topics":"list"}' --json
```
```json
{
  "url": "https://en.wikipedia.org/wiki/Web_scraping",
  "data": {
    "title": "Web scraping",
    "first_sentence": "Web scraping, web harvesting, or web data extraction is data scraping used for extracting data from websites.",
    "key_topics": ["web harvesting", "data scraping", "web crawling", "techniques", "legal issues"]
  },
  "raw": false
}
```

Same call with a natural-language target instead of a schema:

```bash
$ python -m agentcurl https://example.com --extract "the title and a one-line summary"
```

Or switch to a fallback chain — try cheap `static` first, fall through to the
remote `jina` reader only if it comes back empty:

```bash
$ CRAWL_BACKEND=static+jina ROUTER_MODE=fallback python -m agentcurl https://example.com
# backend=router(static+jina); the result is tagged metadata["router_backend"]="static"
```

## Why this shape

- **One contract, not one feature set.** Every backend satisfies the same
  `CrawlBackend` Protocol — `fetch(url) -> Document` and `crawl(url) -> [Document]`
  over a lowest-common-denominator `Document`
  (`url, status, markdown, html, title, links, metadata`). Backend superpowers
  (Firecrawl screenshots, crawl4ai fit-markdown scores) ride in `metadata` rather
  than widening the contract, so swapping engines is a config change, not a code
  change.
- **Zero-dep default, heavy stuff opt-in.** `static` (httpx + trafilatura) needs
  nothing extra and handles most static HTML in milliseconds. You only install
  Playwright / crawl4ai — or wire up a Firecrawl key — when a site actually
  demands it.
- **Crawl for free.** A `CrawlMixin` gives every backend a same-domain
  breadth-first `crawl()` built on its own `fetch()`, so a backend that only
  knows how to fetch one page still crawls. Engines with native deep-crawl
  (crawl4ai, firecrawl) override it.
- **Extraction is core, and degrades gracefully.** `extract` is a first-class
  layer, not an afterthought — and with no key (or any LLM error) it returns raw
  markdown instead of failing.

```
CrawlManager (facade)                                     manager.py
 ├─ CrawlBackend   pluggable, switched by CRAWL_BACKEND    backends/
 │    ├─ static     httpx + trafilatura → markdown   (zero-dep DEFAULT)
 │    ├─ browser    Playwright headless Chromium (JS / dynamic)
 │    ├─ crawl4ai   crawl4ai: fit-markdown + native deep crawl
 │    ├─ firecrawl  Firecrawl managed REST API (scrape / crawl)
 │    ├─ jina       r.jina.ai reader (zero-install remote URL → md)
 │    └─ router     fallback chain / fan-out across the above (a+b)
 ├─ Extractor     DeepSeek-V4-Flash: page → schema/NL prompt → JSON   extract.py
 └─ DeepSeekLLM   one OpenAI-compatible client, injected into the Extractor   llm.py
```

## Backends

| `CRAWL_BACKEND` | What it is | Install | Best for | Live? |
|---|---|---|---|:---:|
| `static` *(default)* | httpx + trafilatura → markdown | none (core) | static HTML, ms/page, CPU-only | ✅ |
| `browser` | Playwright headless Chromium | `pip install "agentcurl[browser]"` + `playwright install chromium` | JS / dynamic pages | ✅ |
| `crawl4ai` | crawl4ai: fit-markdown + native deep crawl | `pip install "agentcurl[crawl4ai]"` + `crawl4ai-setup` | LLM-native crawling at depth | ✅ |
| `firecrawl` | Firecrawl managed REST API | set `FIRECRAWL_API_KEY` | anti-bot / proxy escape hatch | offline-tested |
| `jina` | r.jina.ai remote reader | none (key optional) | zero-install URL → markdown | ✅ |

"Live?" = exercised end-to-end against real sites (see [Verify](#verify)).
`firecrawl` is code-complete and unit-tested but needs a paid key to run live.

**Router.** Set `CRAWL_BACKEND` to a `+`-list (e.g. `static+browser+firecrawl`)
to wrap the children in a `RouterBackend` — itself a `CrawlBackend`, so nothing
else changes:

- `ROUTER_MODE=fallback` *(default)* — try children in order, return the **first
  non-empty** result. Start cheap (`static`), fall through to heavier/remote
  engines only when a page comes back empty.
- `ROUTER_MODE=fan-out` — query **all** children, return the richest
  (longest-markdown) result.

A child that errors or returns empty is skipped (the error is recorded on
`router.errors`); if every child raises, the last error propagates. The winning
result is tagged with `metadata["router_backend"]`.

## Structured extraction

`extract(url | Document, target)` fetches via the active backend, then asks
DeepSeek to return JSON. `target` is either:

- a **dict schema** — `{"title": "str", "price": "number"}` (keys → expected types), or
- a **list of fields** — `["title", "author", "published_date"]`, or
- a **natural-language prompt** — `"the article title and author"`.

With no `DEEPSEEK_API_KEY` (or any LLM/parse error) it returns the raw markdown
with `ExtractResult.raw == True`, so the pipeline never crashes offline.

## Install

```bash
pip install -e .                       # core: httpx, trafilatura, openai, dotenv
# pip install -e ".[browser]"          # + Playwright   (then: playwright install chromium)
# pip install -e ".[crawl4ai]"         # + crawl4ai      (then: crawl4ai-setup)
# pip install -e ".[all]"              # everything
cp .env.example .env                   # add DEEPSEEK_API_KEY for extraction
```

`requirements-local-cpu.txt` documents the CPU-only verified set on macbook-m3
(arm64) and ubuntu, including the one-time browser downloads and the ubuntu
headless system-lib note. All local backends run CPU-only — no GPU anywhere.

## Quickstart

```bash
python demo.py                                   # fetch + extract, fully offline-capable
python -m agentcurl https://example.com          # print clean markdown
python -m agentcurl https://example.com --extract "the title and a one-line summary"
python -m agentcurl https://example.com --schema '{"title":"str"}' --json
python -m agentcurl https://example.com --crawl --depth 1 --max-pages 5
```

### Switching backends

```bash
CRAWL_BACKEND=static   python demo.py   # default, no extra install
CRAWL_BACKEND=jina     python demo.py   # remote reader, zero install (JS handled remotely)
CRAWL_BACKEND=browser  python demo.py   # JS page via Playwright  (needs: playwright install chromium)
CRAWL_BACKEND=crawl4ai python demo.py   # fit-markdown + deep crawl (needs: crawl4ai-setup)
CRAWL_BACKEND=static+firecrawl ROUTER_MODE=fallback python demo.py   # fallback chain
```

## Verify

```bash
python tests/test_smoke.py        # offline: real static fetch/crawl over a loopback fixture
                                  # server + router/extractor/factory units (14 tests)
RUN_LIVE=1 python tests/test_live.py   # opt-in: real sites + DeepSeek + installed backends
                                       # (browser/crawl4ai self-skip if not installed)
python benchmark.py --extract static jina crawl4ai   # latency / md size / links / field accuracy
```

The offline suite runs with `ResourceWarning` as an error, so a leaked
connection fails the build. CI (`.github/workflows/ci.yml`) byte-compiles
everything and runs the offline suite on Python 3.10 / 3.11 / 3.12 for every
push and PR — core deps only, no browser. The live suite is never run in CI.

### Benchmark

`benchmark.py` runs a URL set through each backend in isolated subprocesses
(heavy backends interfere when sharing a process). Indicative run (this machine,
2 public URLs — example.com + iana.org; DeepSeek-V4-Flash):

| backend  | fetch(ms) | md(chars) | links | fields¹ |
|----------|----------:|----------:|------:|--------:|
| static   |    ~1990  |      466  |  9.5  |   0.5   |
| jina     |    ~1990  |     1340  |  0.0  |   1.0   |
| crawl4ai |    ~4440  |     1268  |  9.5  |   1.0   |
| browser  |   ~10820  |      466  |  9.5  |   0.5   |

¹ `fields` = fraction of expected schema keys DeepSeek filled. On these two
*sparse* pages trafilatura (static/browser) strips the `<title>`, so `title`
comes back null — `jina`/`crawl4ai` keep richer markdown and fill both. On
content pages all four fill the fields; this is a trait of these minimal test
URLs, not a backend defect. Rules of thumb: speed → `static`; JS → `browser`;
LLM-native depth → `crawl4ai`; zero-install → `jina`; blocked sites →
`firecrawl`. `fetch(ms)` times the fetch only, not the LLM call.

## MCP server

`mcp/server.py` is a stdio MCP server exposing `agentcurl_fetch(url)`,
`agentcurl_crawl(url, depth)` and `agentcurl_extract(url, schema)` — each just
calls `CrawlManager`, so the MCP inherits whatever `CRAWL_BACKEND` selects.
Register it in `~/.claude.json` / Claude Desktop:

```json
{
  "mcpServers": {
    "agentcurl": {
      "command": "python3",
      "args": ["/abs/path/to/agentcurl/mcp/server.py"],
      "env": { "CRAWL_BACKEND": "static" }
    }
  }
}
```

The `server.py` shim loads the repo's own `.env`, so your `DEEPSEEK_API_KEY`
stays in `.env` and out of the client config. After `pip install -e .` you can
instead use `"args": ["-m", "agentcurl.mcp"]`. Verified live over stdio JSON-RPC
(initialize → tools/list → `agentcurl_fetch` → 200). See `mcp/README.md`.

## Claude Code SKILL

`skill/SKILL.md` (`agentcurl`) is a thin conversational layer that shells out to
`python -m agentcurl <url> --extract "<prompt>"`. Copy it to
`~/.claude/skills/agentcurl/` and ask: *"/agentcurl crawl example.com and pull
the title and summary"*. Run `pip install -e .` so `python -m agentcurl` resolves
from any directory.

## Configuration (env / `.env`)

| Var | Default | Meaning |
|-----|---------|---------|
| `DEEPSEEK_API_KEY` | — | DeepSeek key (OpenAI-compatible); empty → extraction falls back to raw markdown |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | model id |
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com` | base url |
| `CRAWL_BACKEND` | `static` | `static` \| `browser` \| `crawl4ai` \| `firecrawl` \| `jina` \| a `+`-list e.g. `static+jina` |
| `ROUTER_MODE` | `fallback` | for a `+`-list: `fallback` (first non-empty) \| `fan-out` (richest) |
| `CRAWL_DEPTH` | `1` | link-following depth for `crawl()` |
| `CRAWL_MAX_PAGES` | `20` | hard cap on pages per `crawl()` |
| `REQUEST_TIMEOUT` | `30` | per-request HTTP timeout (seconds) |
| `RATE_LIMIT_DELAY` | `0` | seconds between same-domain fetches (be polite) |
| `RESPECT_ROBOTS` | `1` | honor robots.txt on the link-walk crawl |
| `FIRECRAWL_API_KEY` | — | required for the `firecrawl` backend |
| `JINA_API_KEY` | — | optional; raises r.jina.ai rate limits |

Full set with browser/crawl4ai tunables in `.env.example`.

## Notes & limits

- **Offline-friendly:** the `static` backend + the raw-markdown extraction
  fallback run with no key and no network beyond the target site. The offline
  test suite needs neither (it serves fixtures over loopback).
- **Politeness:** the link-walk crawl honors `robots.txt` (fail-open if it can't
  be fetched) and the `RATE_LIMIT_DELAY` throttle. Native deep-crawl backends
  manage their own fetching.
- **Connection reuse:** the `static` backend keeps one pooled `httpx.Client`
  across a crawl (keep-alive); `with CrawlManager() as cm:` releases it.
- **Charset detection:** legacy sites (e.g. GBK/GB2312 Chinese pages) that send
  no charset header are decoded via their `<meta charset>` like a browser would,
  so `static` doesn't mojibake them. JS-rendered pages (YouTube, SPAs) still need
  `browser`, `crawl4ai`, or the remote `jina` reader — `static` only sees the
  initial HTML shell.
- **One heavy backend per process:** Playwright and crawl4ai drive real browsers
  — the live tests isolate each in its own subprocess.

## Out of scope (v1)

Proxy rotation / stealth anti-bot (use **firecrawl** as the escape hatch) and
distributed/queue-based large crawls (Scrapy/Crawlee) — use **crawl4ai** or
**firecrawl** native deep-crawl instead.

## Layout

```
src/agentcurl/
  manager.py            CrawlManager facade: fetch / crawl / extract + lifecycle
  extract.py            DeepSeek schema/NL → JSON (+ offline raw fallback)
  llm.py                DeepSeek-V4-Flash OpenAI-compatible client
  fetch_utils.py        pooled GET, robots.txt gate, link extraction, rate limit
  config.py             env-driven config
  types.py              Document, ExtractResult
  mcp.py                MCP server (agentcurl_fetch / _crawl / _extract)
  backends/
    base.py             CrawlBackend Protocol + CrawlMixin (default crawl)
    static.py           httpx + trafilatura  (default)
    browser.py          Playwright
    crawl4ai_backend.py crawl4ai (native deep-crawl)
    firecrawl_backend.py Firecrawl REST
    jina_backend.py     r.jina.ai reader
    router.py           fallback chain / fan-out
demo.py · benchmark.py · mcp/server.py · skill/SKILL.md · tests/
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — dev setup, the offline/live test split,
and a step-by-step guide to adding a new crawl backend behind the `CrawlBackend`
Protocol.

## License

[MIT](LICENSE)
