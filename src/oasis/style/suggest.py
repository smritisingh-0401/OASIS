"""Notices indirect phrasing and suggests the indirect style; never applies it (FR-CUL-2)."""

from __future__ import annotations

import functools
import re
from collections.abc import Sequence

from oasis.style.framing import load_framing
from oasis.types import StyleProfile


@functools.cache
def _pattern() -> re.Pattern[str]:
    words = sorted(load_framing().hedges, key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b")


def hedged(message: str) -> bool:
    # Known limit: a phrase list ("what kind of music" counts); the 2-of-3 window keeps one
    # stray match from suggesting anything. A labelled set would tell whether more is needed.
    text = " ".join(re.sub(r"['\u2019]", "", message.lower()).split())
    return bool(_pattern().search(text))


def suggest(message: str, earlier: Sequence[str], style: StyleProfile) -> bool:
    """True when this message and enough of the ones just before it are hedged. `earlier` is
    the user's previous typed messages, oldest first."""
    if style.directness == "indirect" or not hedged(message):
        return False
    cfg = load_framing()
    return sum(map(hedged, [*earlier, message][-cfg.window :])) >= cfg.min_hedged
