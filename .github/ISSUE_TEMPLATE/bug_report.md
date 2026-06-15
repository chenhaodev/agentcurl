---
name: Bug report
about: Something isn't working as expected
title: "[bug] "
labels: bug
---

**What happened**
A clear description of the bug, and what you expected instead.

**Repro**
Minimal steps or code:

```python
from agentcurl import CrawlManager
# ...
```

Or the CLI command: `python -m agentcurl <url> ...`

**Config**
- Crawl backend (`CRAWL_BACKEND`): <!-- static | browser | crawl4ai | firecrawl | jina | a+b -->
- Router mode (`ROUTER_MODE`, if a "+"-list): <!-- fallback | fan-out -->
- Was extraction involved (DeepSeek)? <!-- yes/no -->

**Environment**
- agentcurl version / commit:
- Python version:
- OS:
- Backend lib version (if browser/crawl4ai): <!-- playwright / crawl4ai -->

**Logs / traceback**
```
paste here
```

**Checklist**
- [ ] Reproduces with the offline `static` backend (helps isolate backend vs core), or noted why not
- [ ] `python tests/test_smoke.py` passes on my machine
