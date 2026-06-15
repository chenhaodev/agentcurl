"""Benchmark the crawl backends on a shared URL set.

Each backend runs in its OWN subprocess (browser/crawl4ai drive heavy resources
that interfere when sharing a process; isolation also keeps timings clean).

    set -a && . ./.env && set +a
    export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")
    python benchmark.py                          # default backends
    python benchmark.py static jina firecrawl    # pick backends
    python benchmark.py --extract static         # also score field extraction

Metrics per backend (averaged over the URL set):
  fetch(ms)  wall-clock latency per page
  md(chars)  markdown size (content richness)
  links      links discovered per page
  fields     fraction of expected extraction fields filled (with --extract,
             needs DEEPSEEK_API_KEY) — measures extraction quality.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, "src")

# (url, schema, expected-non-null fields) — small, stable, public pages.
URLS = [
    ("https://example.com", {"title": "str", "summary": "str"}, ["title"]),
    ("https://www.iana.org/help/example-domains", {"title": "str", "summary": "str"}, ["title"]),
]


def run_one(backend: str, do_extract: bool) -> dict:
    from agentcurl import Config, CrawlManager

    cfg = Config.from_env()
    cfg.crawl_backend = backend
    cm = CrawlManager(cfg)

    latencies, md_sizes, link_counts = [], [], []
    field_hits = field_total = 0
    try:
        for url, schema, expected in URLS:
            t = time.perf_counter()
            doc = cm.fetch(url)
            latencies.append((time.perf_counter() - t) * 1000)
            md_sizes.append(len(doc.markdown))
            link_counts.append(len(doc.links))
            if do_extract:
                res = cm.extract(doc, schema)
                data = res.data if isinstance(res.data, dict) else {}
                for f in expected:
                    field_total += 1
                    if data.get(f):
                        field_hits += 1

        n = len(URLS)
        row = {
            "backend": backend, "ok": True,
            "fetch_ms": round(sum(latencies) / n, 1),
            "md_chars": round(sum(md_sizes) / n),
            "links": round(sum(link_counts) / n, 1),
        }
        if do_extract:
            row["fields"] = round(field_hits / field_total, 2) if field_total else 0.0
        return row
    except Exception as e:
        return {"backend": backend, "ok": False, "error": repr(e)[:300]}


def _print_table(rows: list[dict], do_extract: bool) -> None:
    print("\n" + "=" * 72)
    header = f"{'backend':<12}{'fetch(ms)':>11}{'md(chars)':>11}{'links':>8}"
    if do_extract:
        header += f"{'fields':>8}"
    print(header)
    print("-" * 72)
    for r in rows:
        if r.get("ok"):
            line = f"{r['backend']:<12}{r['fetch_ms']:>11}{r['md_chars']:>11}{r['links']:>8}"
            if do_extract:
                line += f"{r.get('fields', 0.0):>8}"
            print(line)
        else:
            print(f"{r['backend']:<12}{'ERROR':>11}  {r.get('error', '')[:42]}")
    print("=" * 72)
    print(f"{len(URLS)} URL(s). fields = fraction of expected schema keys filled "
          "(needs --extract + DEEPSEEK_API_KEY).")


def main(backends: list[str], do_extract: bool) -> None:
    import subprocess

    rows = []
    for b in backends:
        print(f"running {b} (isolated subprocess) ...", flush=True)
        argv = [sys.executable, __file__, "--one", b] + (["--extract"] if do_extract else [])
        p = subprocess.run(argv, env=os.environ, capture_output=True, text=True)
        lines = [l for l in p.stdout.splitlines() if l.strip().startswith("{")]
        rows.append(
            json.loads(lines[-1]) if lines
            else {"backend": b, "ok": False, "error": (p.stderr or p.stdout)[-120:]}
        )
    _print_table(rows, do_extract)


if __name__ == "__main__":
    do_extract = "--extract" in sys.argv
    rest = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--one" in sys.argv:
        one = sys.argv[sys.argv.index("--one") + 1]
        print(json.dumps(run_one(one, do_extract)))
    else:
        main(rest or ["static", "jina"], do_extract)
