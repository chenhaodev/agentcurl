# agentcurl MCP server

A stdio [MCP](https://modelcontextprotocol.io) server that exposes the
`CrawlManager` over three tools. It's a thin wrapper — the backend is whatever
`CRAWL_BACKEND` selects, so the MCP inherits every tier (static, browser,
crawl4ai, firecrawl, jina, or a router chain).

## Tools

| Tool | Args | Returns |
|---|---|---|
| `agentcurl_fetch` | `url` | one page: markdown + title + links + metadata (JSON) |
| `agentcurl_crawl` | `url`, `depth=1`, `max_pages=20` | one summary per crawled page (JSON array) |
| `agentcurl_extract` | `url`, `schema` | DeepSeek structured JSON (`schema` = JSON object string **or** a natural-language instruction) |

## Install

```bash
pip install -r ../requirements.txt
pip install "mcp[cli]"          # the MCP SDK
```

## Register (Claude Code `~/.claude.json` or Claude Desktop)

Module form (after `pip install -e .` in the repo root):

```json
{
  "mcpServers": {
    "agentcurl": {
      "command": "python",
      "args": ["-m", "agentcurl.mcp"],
      "env": { "CRAWL_BACKEND": "static", "DEEPSEEK_API_KEY": "sk-..." }
    }
  }
}
```

Bare-checkout form (no install needed) — point at this file with an absolute path:

```json
{
  "mcpServers": {
    "agentcurl": {
      "command": "python",
      "args": ["/abs/path/to/agentcurl/mcp/server.py"],
      "env": { "CRAWL_BACKEND": "static" }
    }
  }
}
```

## Try it

From Claude Code, after registering: ask it to call `agentcurl_fetch` on a URL
and confirm clean markdown comes back. Switch backends by changing the
`CRAWL_BACKEND` env in the registration (e.g. `browser`, `static+firecrawl`).
