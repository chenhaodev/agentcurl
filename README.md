# agentcurl

A **switchable web-crawler middleware**: one common interface over five pluggable
crawl backends, switched by a single env var, with a zero-dependency default,
heavier optional backends, a router that chains/fans-out, and DeepSeek-V4-Flash
for structured extraction. Drive it from **repo code**, an **MCP server**, or a
**Claude Code SKILL** — they're all thin wrappers over the same `CrawlManager`.

Sibling project of [agentmem](https://github.com/chenhaodev/agentmem) and built on
the same shape: *one interface, many pluggable backends, env-switched.*

**Status:** verified live — `static`, `browser` (Playwright), `crawl4ai`
(fit-markdown + native deep-crawl), and `jina`, plus DeepSeek-V4-Flash structured
extraction, all run end-to-end against real sites. `firecrawl` is code-complete
but exercised only offline (needs a paid API key).

```python
from agentcurl import CrawlManager

# CrawlManager is a context manager — `with` releases pooled connections cleanly
with CrawlManager() as cm:                           # backend chosen by CRAWL_BACKEND
    doc = cm.fetch("https://example.com")            # -> Document (markdown + links + meta)
    docs = cm.crawl("https://example.com", depth=1)  # -> list[Document]
    res = cm.extract(doc, {"title": "str", "price": "number"})  # -> ExtractResult (JSON)
```

## Backends

| `CRAWL_BACKEND` | What it is | Install | Best for |
|---|---|---|---|
| `static` *(default)* | httpx + trafilatura → markdown | none (core) | static HTML, ms/page, CPU-only |
| `browser` | Playwright headless Chromium | `pip install "agentcurl[browser]"` + `playwright install chromium` | JS / dynamic pages |
| `crawl4ai` | crawl4ai: fit-markdown + native deep crawl | `pip install "agentcurl[crawl4ai]"` + `crawl4ai-setup` | LLM-native crawling at depth |
| `firecrawl` | Firecrawl managed REST API | set `FIRECRAWL_API_KEY` | anti-bot / proxy escape hatch |
| `jina` | r.jina.ai remote reader | none (key optional) | zero-install URL→markdown |

**Router**: set `CRAWL_BACKEND` to a `+`-list (e.g. `static+browser+firecrawl`) to
get a `RouterBackend`. With `ROUTER_MODE=fallback` (default) it tries each child
in order and returns the first non-empty result — start cheap, fall through to
heavier/remote backends only when needed. `ROUTER_MODE=fan-out` queries all and
returns the richest (longest-markdown) result. A child that errors or returns
empty is skipped; if every child fails, the last error propagates.

## Structured extraction

`extract(url | Document, target)` fetches via the active backend, then asks
DeepSeek-V4-Flash to return JSON. `target` is either a **dict schema**
(`{"title": "str", "price": "number"}`) or a **natural-language prompt**
(`"the article title and author"`). With no `DEEPSEEK_API_KEY` (or any LLM
error) it degrades gracefully to returning the raw markdown — the pipeline never
crashes offline.

## Install

```bash
pip install -r requirements.txt        # core: httpx, trafilatura, openai, dotenv
cp .env.example .env                   # add DEEPSEEK_API_KEY for extraction
```

See `requirements-local-cpu.txt` for the CPU-only verified set on macbook-m3
(arm64) and ubuntu, including the `playwright install chromium` /
`crawl4ai-setup` browser steps and the ubuntu headless system-lib note.

## Quickstart

```bash
python demo.py                                   # fetch + extract, fully offline-capable
python -m agentcurl https://example.com          # print markdown
python -m agentcurl https://example.com --extract "the title and a one-line summary"
python -m agentcurl https://example.com --schema '{"title":"str"}' --json
python -m agentcurl https://example.com --crawl --depth 1 --max-pages 5

CRAWL_BACKEND=browser python demo.py             # JS page via Playwright
CRAWL_BACKEND=static+firecrawl ROUTER_MODE=fallback python demo.py   # fallback chain
```

## Verify

```bash
python tests/test_smoke.py        # offline: real static fetch/crawl over a loopback
                                  # fixture server + router/extractor/factory units (14 tests)
RUN_LIVE=1 python tests/test_live.py   # opt-in: real sites + DeepSeek + installed backends
                                       # (browser/crawl4ai self-skip if not installed)
python benchmark.py               # latency / md size / links per backend
python benchmark.py --extract static jina crawl4ai   # also score extraction-field accuracy
```

The offline suite runs with `ResourceWarning` as an error, so a leaked
connection fails the build. See [CONTRIBUTING.md](CONTRIBUTING.md) for the
backend-extension guide.

### Benchmark (measured live, 2 public URLs — example.com + iana.org; your numbers vary by network)

| backend | fetch(ms) | md(chars) | links | fields¹ |
|---|---|---|---|---|
| static | ~1990 | 466 | 9.5 | 0.5 |
| jina | ~1990 | 1340 | 0 | 1.0 |
| crawl4ai | ~4440 | 1268 | 9.5 | 1.0 |
| browser | ~10820 | 466 | 9.5 | 0.5 |

¹ `fields` = fraction of expected schema keys DeepSeek filled. On these two
sparse pages, trafilatura (static/browser) strips the `<title>`, so the `title`
field comes back null — `jina`/`crawl4ai` keep richer markdown and fill both.
On content pages all four fill the fields; this is a known trait of these
minimal test URLs, not a backend defect. `fetch(ms)` times the fetch only, not
the LLM call.

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
stays in `.env` and out of the client config. If you `pip install -e .`, you can
instead use `"command": "python3", "args": ["-m", "agentcurl.mcp"]`. Verified
live over stdio JSON-RPC (initialize → tools/list → `agentcurl_fetch` → 200).
See `mcp/README.md`.

## Claude Code SKILL

`skill/SKILL.md` (`agentcurl`) is a thin conversational layer that shells out to
`python -m agentcurl <url> --extract "<prompt>"`. Copy `skill/SKILL.md` to
`~/.claude/skills/agentcurl/` and ask: *"/agentcurl crawl example.com and pull
the title and summary"*. Run `pip install -e .` so `python -m agentcurl` and the
`agentcurl` console script resolve from any directory.

## Cross-platform (m3 / ubuntu)

- `static` / `jina` / `firecrawl`: pure-python or remote → identical on both.
- `browser` / `crawl4ai`: need a one-time browser download
  (`playwright install chromium` / `crawl4ai-setup`). On arm64 macOS the arm64
  Chromium is pulled automatically; on ubuntu headless also install the system
  libs (`playwright install-deps chromium`). All local backends run CPU-only.

## Out of scope (v1)

Proxy rotation / stealth anti-bot (use **firecrawl** as the escape hatch) and
distributed/queue-based large crawls (Scrapy/Crawlee) — use **crawl4ai** or
**firecrawl** native deep-crawl instead.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — dev setup, the offline/live test split,
and a step-by-step guide to adding a new crawl backend behind the `CrawlBackend`
Protocol.

## License

[MIT](LICENSE)
