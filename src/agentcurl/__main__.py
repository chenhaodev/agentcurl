"""`python -m agentcurl <url> [--extract PROMPT|--schema JSON] [--crawl]`

A tiny CLI over CrawlManager. The Claude Code SKILL shells out to this, so it
stays a thin conversational layer. Uses whatever CRAWL_BACKEND is configured
(defaults to the offline-friendly static backend).

    python -m agentcurl https://example.com
    python -m agentcurl https://example.com --extract "the page title and summary"
    python -m agentcurl https://example.com --schema '{"title":"str","links":"list"}'
    python -m agentcurl https://example.com --crawl --depth 1 --max-pages 5
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from .manager import CrawlManager
from .types import Document, ExtractResult


def _doc_dict(doc: Document) -> dict:
    return dataclasses.asdict(doc)


def _result_dict(res: ExtractResult) -> dict:
    return dataclasses.asdict(res)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentcurl", description=__doc__)
    parser.add_argument("url", help="URL to fetch / crawl / extract from")
    parser.add_argument("--extract", metavar="PROMPT", help="natural-language extraction instruction")
    parser.add_argument("--schema", metavar="JSON", help="JSON schema of fields to extract")
    parser.add_argument("--crawl", action="store_true", help="crawl the site instead of one page")
    parser.add_argument("--depth", type=int, default=None, help="crawl link-following depth")
    parser.add_argument("--max-pages", type=int, default=None, help="crawl page cap")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of pretty text")
    args = parser.parse_args(argv)

    cm = CrawlManager()

    if args.extract or args.schema:
        target = json.loads(args.schema) if args.schema else args.extract
        res = cm.extract(args.url, target)
        if args.json:
            print(json.dumps(_result_dict(res), indent=2, ensure_ascii=False))
        else:
            print(f"# extract {res.url}  ({'raw markdown' if res.raw else 'json'})")
            print(res.data if res.raw else json.dumps(res.data, indent=2, ensure_ascii=False))
        return 0

    if args.crawl:
        docs = cm.crawl(args.url, depth=args.depth, max_pages=args.max_pages)
        if args.json:
            print(json.dumps([_doc_dict(d) for d in docs], indent=2, ensure_ascii=False))
        else:
            print(f"# crawled {len(docs)} page(s) via {cm.backend.name}")
            for d in docs:
                print(f"  - {d.url}  ({d.status}, {len(d.markdown)} md chars, {len(d.links)} links)")
        return 0

    doc = cm.fetch(args.url)
    if args.json:
        print(json.dumps(_doc_dict(doc), indent=2, ensure_ascii=False))
    else:
        print(f"# {doc.title or doc.url}  (backend={cm.backend.name}, status={doc.status})")
        print(doc.markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
