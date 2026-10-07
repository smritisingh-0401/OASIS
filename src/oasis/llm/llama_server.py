"""Client for llama.cpp `llama-server` (OpenAI-compatible chat endpoint) in a separate process."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from oasis.llm.client import LLMFailure
from oasis.types import ChatMessage


class LlamaServerClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        connect_timeout_s: float,
        sampling: Mapping[str, float | int],
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._model = model
        self._connect_timeout_s = connect_timeout_s
        self._sampling = dict(sampling)
        self._http = httpx.AsyncClient(base_url=base_url, transport=transport)

    async def generate(
        self, messages: Sequence[ChatMessage], *, max_tokens: int, timeout_s: float
    ) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": max_tokens,
            "stream": False,
            # Qwen3.5 reasons by default; reasoning text must never reach the user.
            # Requires llama-server started with --jinja.
            "chat_template_kwargs": {"enable_thinking": False},
            **self._sampling,
        }
        timeout = httpx.Timeout(timeout_s, connect=self._connect_timeout_s)
        try:
            resp = await self._http.post("/v1/chat/completions", json=payload, timeout=timeout)
        except httpx.ConnectError:
            raise LLMFailure("down") from None
        except httpx.TimeoutException:
            raise LLMFailure("timeout") from None
        except httpx.HTTPError:
            raise LLMFailure("http_error") from None
        if resp.status_code != 200:
            raise LLMFailure("http_error")
        try:
            # Only `content` is read; any separate `reasoning_content` field is ignored.
            content = resp.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise LLMFailure("bad_response") from None
        if not isinstance(content, str):
            raise LLMFailure("bad_response")
        return content

    async def health(self) -> bool:
        try:
            resp = await self._http.get("/health", timeout=self._connect_timeout_s)
        except httpx.HTTPError:
            return False
        return resp.status_code == 200

    async def aclose(self) -> None:
        await self._http.aclose()
