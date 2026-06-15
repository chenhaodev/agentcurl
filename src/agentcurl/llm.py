"""DeepSeek-V4-Flash client via the OpenAI-compatible endpoint.

DeepSeek V4 speaks the OpenAI ChatCompletions API at https://api.deepseek.com,
so we reuse the official `openai` SDK and just repoint base_url. One shared
instance is injected into the Extractor. Copied near-verbatim from agentmem so
the two projects stay consistent.
"""

from __future__ import annotations

from typing import Any

from .config import Config


class DeepSeekLLM:
    def __init__(self, config: Config):
        self.config = config
        self.model = config.deepseek_model
        self._client = None  # lazy: don't import openai until first use

    @property
    def available(self) -> bool:
        """Whether a key is configured. Lets callers pick the offline path
        without paying for a doomed network round-trip."""
        return bool(self.config.deepseek_api_key)

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.config.deepseek_api_key,
                base_url=self.config.deepseek_base_url,
                timeout=self.config.deepseek_timeout,
                max_retries=self.config.deepseek_max_retries,
            )
        return self._client

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages, **kwargs
        )
        return resp.choices[0].message.content or ""
