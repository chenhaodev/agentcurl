"""LLM structured extraction — page markdown -> validated JSON.

A ScrapeGraphAI-style layer on top of any backend: take a fetched Document and a
target (either a dict schema like {"title": "str", "price": "number"} or a
natural-language prompt) and ask DeepSeek to return matching JSON. Mirrors
agentmem's no-key path: with no DEEPSEEK_API_KEY (or any LLM failure) it
degrades to returning the raw markdown so the pipeline still runs offline.
"""

from __future__ import annotations

import json
from typing import Any

from .llm import DeepSeekLLM
from .types import Document, ExtractResult

# Cap the markdown we send so a huge page can't blow the context window / cost.
_MAX_CHARS = 24_000

_SCHEMA_SYS = (
    "You extract structured data from a web page's markdown. The user gives a "
    "JSON schema (keys -> expected types) and the page content. Respond ONLY "
    "with a JSON object whose keys exactly match the schema. Use null for any "
    "field you cannot find. Do not invent values."
)

_PROMPT_SYS = (
    "You extract structured data from a web page's markdown according to the "
    "user's instruction. Respond ONLY with a single JSON object (or array) "
    "containing the requested data. Use null for anything not present."
)


def _truncate(markdown: str) -> str:
    return markdown if len(markdown) <= _MAX_CHARS else markdown[:_MAX_CHARS]


def parse_target(text: str) -> Any:
    """Normalize a CLI/MCP string into an extraction target: a JSON object/list
    becomes a schema; anything else stays a natural-language prompt string."""
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
    return parsed if _is_schema(parsed) else text


def _is_schema(target: Any) -> bool:
    """A schema is a dict (field -> type) or a list of field names. A plain
    string is a natural-language instruction, not a schema."""
    return isinstance(target, (dict, list))


def _schema_fields(target: Any) -> list[str]:
    if isinstance(target, dict):
        return list(target.keys())
    if isinstance(target, list):
        return [str(f) for f in target]
    return []


class Extractor:
    """Wraps a DeepSeekLLM to turn pages into JSON. Stateless apart from the LLM."""

    def __init__(self, llm: DeepSeekLLM):
        self.llm = llm

    def extract(self, document: Document, target: Any) -> ExtractResult:
        """`target` is a dict schema or a natural-language string prompt."""
        markdown = document.markdown or document.html
        fields = _schema_fields(target)

        if not self.llm.available or not markdown.strip():
            # Offline / no-key / empty-page fallback: hand back the raw markdown.
            return ExtractResult(
                url=document.url,
                data=markdown,
                fields=fields,
                raw=True,
                metadata={"reason": "no_llm_key_or_empty_page"},
            )

        try:
            data = self._call_llm(markdown, target)
            return ExtractResult(url=document.url, data=data, fields=fields, raw=False)
        except Exception as e:
            # Any LLM/parse failure -> graceful raw fallback (never crash a crawl).
            return ExtractResult(
                url=document.url,
                data=markdown,
                fields=fields,
                raw=True,
                metadata={"reason": "llm_error", "error": repr(e)[:200]},
            )

    def _call_llm(self, markdown: str, target: Any) -> Any:
        if _is_schema(target):
            system = _SCHEMA_SYS
            user = (
                f"JSON schema:\n{json.dumps(target)}\n\n"
                f"Page markdown:\n{_truncate(markdown)}"
            )
        else:
            system = _PROMPT_SYS
            user = (
                f"Instruction: {target}\n\n"
                f"Page markdown:\n{_truncate(markdown)}"
            )
        out = self.llm.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        return json.loads(out)
