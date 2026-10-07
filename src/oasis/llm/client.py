"""LLM client interface, typed failure, reply cleaning and the bounded request queue."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from typing import Protocol

from oasis.types import ChatMessage


class LLMFailure(Exception):
    """Any reason the model did not produce a usable draft. `reason` feeds the trace."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class LLMClient(Protocol):
    async def generate(
        self, messages: Sequence[ChatMessage], *, max_tokens: int, timeout_s: float
    ) -> str: ...

    async def health(self) -> bool: ...

    async def aclose(self) -> None: ...


_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.IGNORECASE | re.DOTALL)
_THINK_CLOSE = re.compile(r"</think", re.IGNORECASE)
_THINK_OPEN = re.compile(r"<think", re.IGNORECASE)


def clean_reply(raw: str) -> str:
    """Remove every trace of model reasoning; empty result is a failure.

    Handles complete blocks, a closing tag with no opening tag (everything before it is
    reasoning) and an unterminated opening tag (everything after it is reasoning).
    """
    text = _THINK_BLOCK.sub("", raw)
    closes = list(_THINK_CLOSE.finditer(text))
    if closes:
        last_close = closes[-1]
        end = text.find(">", last_close.end())
        text = text[end + 1 :] if end != -1 else ""
    opening = _THINK_OPEN.search(text)
    if opening is not None:
        text = text[: opening.start()]
    # Collapse the gaps left by removed blocks without touching paragraph breaks.
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    if not text:
        raise LLMFailure("empty")
    return text


class BoundedLLM:
    """Caps in-flight and waiting requests; beyond the cap it fails fast with "busy".

    A CPU-bound llama-server handles one generation at a time well; queuing without a
    limit would turn a traffic burst into every user waiting past the request timeout.
    """

    def __init__(self, inner: LLMClient, *, max_concurrency: int, queue_limit: int) -> None:
        self._inner = inner
        self._slots = asyncio.Semaphore(max_concurrency)
        self._capacity = max_concurrency + queue_limit
        self._pending = 0

    async def generate(
        self, messages: Sequence[ChatMessage], *, max_tokens: int, timeout_s: float
    ) -> str:
        if self._pending >= self._capacity:
            raise LLMFailure("busy")
        self._pending += 1
        try:
            async with self._slots:
                return await self._inner.generate(
                    messages, max_tokens=max_tokens, timeout_s=timeout_s
                )
        finally:
            self._pending -= 1

    async def health(self) -> bool:
        return await self._inner.health()

    async def aclose(self) -> None:
        await self._inner.aclose()
