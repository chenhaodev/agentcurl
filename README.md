# agentcurl

A **switchable web-crawler middleware**: one common interface over five pluggable
crawl backends, switched by a single env var, with a zero-dependency default,
heavier optional backends, a router that chains/fans-out, and DeepSeek-V4-Flash
for structured extraction. Drive it from **repo code**, an **MCP server**, or a
**Claude Code SKILL** — they're all thin wrappers over the same `CrawlManager`.

Sibling project of [agentmem](https://github.com/chenhaodev/agentmem) and built on
the same shape: *one interface, many pluggable backends, env-switched.*

```python
from agentcurl import CrawlManager

cm = CrawlManager()                              # backend chosen by CRAWL_BACKEND
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
                                  # fixture server + router/extractor/factory units
RUN_LIVE=1 python tests/test_live.py   # opt-in: real sites + DeepSeek + remote backends
python benchmark.py               # latency / md size / links per backend
python benchmark.py --extract static jina    # also score extraction-field accuracy
```

### Benchmark (example shape — your numbers vary by network)

| backend | fetch(ms) | md(chars) | links | fields |
|---|---|---|---|---|
| static | ~120 | ~1500 | ~3 | 1.0 |
| jina | ~900 | ~1400 | 0 | 1.0 |

## MCP server

`mcp/server.py` is a stdio MCP server exposing `agentcurl_fetch(url)`,
`agentcurl_crawl(url, depth)` and `agentcurl_extract(url, schema)` — each just
calls `CrawlManager`, so the MCP inherits whatever `CRAWL_BACKEND` selects.
Register it in `~/.claude.json` / Claude Desktop:

```json
{
  "mcpServers": {
    "agentcurl": {
      "command": "python",
      "args": ["-m", "agentcurl.mcp"],
      "env": { "CRAWL_BACKEND": "static", "DEEPSEEK_API_KEY": "..." }
    }
  }
}
```

(Or point `command`/`args` at `mcp/server.py` directly.) See `mcp/README.md`.

## Claude Code SKILL

`skill/SKILL.md` (`agentcurl`) is a thin conversational layer that shells out to
`python -m agentcurl <url> --extract "<prompt>"`. Copy `skill/` to
`~/.claude/skills/agentcurl/` and ask: *"/agentcurl crawl example.com and pull
the title and summary"*.

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

## License

MIT
