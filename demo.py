"""End-to-end demo of the agentcurl middleware.

Runs fully offline by default (static backend + extraction that falls back to
raw markdown if DeepSeek is unreachable). With a live DEEPSEEK_API_KEY the
`extract` step does real structured-JSON extraction.

    pip install -r requirements.txt
    python demo.py                              # static backend (no extra deps)
    CRAWL_BACKEND=jina python demo.py           # remote reader, no install
    CRAWL_BACKEND=static+jina ROUTER_MODE=fallback python demo.py   # fallback chain
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "src")

from agentcurl import CrawlManager  # noqa: E402

URL = "https://example.com"
SCHEMA = {"title": "str", "summary": "one-sentence summary of the page"}


def main() -> None:
    with CrawlManager() as cm:
        print(f"== agentcurl demo ==  backend: {cm.backend.name}\n")

        print(f"-- fetch {URL} --")
        doc = cm.fetch(URL)
        print(f"  status={doc.status}  title={doc.title!r}  "
              f"{len(doc.markdown)} md chars  {len(doc.links)} links")
        print("  markdown preview:")
        for line in doc.markdown.splitlines()[:6]:
            print(f"    {line}")

        print(f"\n-- extract {SCHEMA} --")
        res = cm.extract(doc, SCHEMA)
        if res.raw:
            print("  (no DEEPSEEK_API_KEY — raw-markdown fallback)")
            print(f"    {res.data[:200]}")
        else:
            print(json.dumps(res.data, indent=2, ensure_ascii=False))

        print("\n-- natural-language extract: 'the main heading on the page' --")
        res2 = cm.extract(doc, "the main heading on the page")
        print(f"  raw={res2.raw}  data={str(res2.data)[:200]}")


if __name__ == "__main__":
    main()
