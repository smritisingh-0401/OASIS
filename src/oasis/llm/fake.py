"""Deterministic stand-in for the model: used by tests and for UI work without weights."""

from __future__ import annotations

import asyncio
import zlib
from collections.abc import Sequence

from oasis.llm.client import LLMFailure
from oasis.llm.prompt import SCRIPT_MARK
from oasis.types import ChatMessage

_DEFAULT_REPLIES = (
    "That sounds like a lot to carry. What feels heaviest about it right now?",
    "That sounds like a lot to hold. How has it been affecting your day?",
    "It makes sense that you'd feel that way. What would help most to talk through?",
)


class FakeLLM:
    def __init__(
        self,
        replies: Sequence[str] | None = None,
        *,
        delay_s: float = 0.0,
        fail: str | None = None,
    ) -> None:
        self._replies = tuple(replies) if replies else None
        self._delay_s = delay_s
        self._fail = fail
        self.calls = 0
        self.last_messages: list[ChatMessage] = []

    async def generate(
        self, messages: Sequence[ChatMessage], *, max_tokens: int, timeout_s: float
    ) -> str:
        self.calls += 1
        self.last_messages = list(messages)
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        if self._fail:
            raise LLMFailure(self._fail)
        if self._replies:
            return self._replies[(self.calls - 1) % len(self._replies)]
        # A real model phrases an exercise step in its own words; the fake says the step
        # itself, so exercises can be followed end to end without model weights.
        system = messages[0].content if messages else ""
        if SCRIPT_MARK in system:
            return system.split(SCRIPT_MARK, 1)[1].split("\n", 1)[0]
        # crc32 rather than hash(): stable across processes, so replies are reproducible.
        key = zlib.crc32(messages[-1].content.encode()) if messages else 0
        return _DEFAULT_REPLIES[key % len(_DEFAULT_REPLIES)]

    async def health(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None
