"""The prompt's style line, from the user's profile (design §13.1 `{style_framing}`)."""

from __future__ import annotations

import functools
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, get_args

from oasis.content import load_yaml, require_review
from oasis.types import Directness, Formality, StyleProfile

STYLE_MARK = "Style: "


@dataclass(frozen=True)
class Framing:
    directness: Mapping[str, str]
    formality: Mapping[str, str]
    window: int  # suggestion: typed messages looked at, this one included
    min_hedged: int
    hedges: tuple[str, ...]
    version: str


def parse_framing(raw: Mapping[str, Any]) -> Framing:
    require_review(raw, "style framing")
    default = StyleProfile()
    for name, values, base in (("directness", Directness, default.directness),
                               ("formality", Formality, default.formality)):  # fmt: skip
        given = raw.get(name) or {}
        if set(given) != set(get_args(values)):
            raise ValueError(f"style framing needs exactly {get_args(values)} for {name}")
        if given[base]:
            raise ValueError(f"the default {name} ({base}) must add no framing")
    suggest = raw["suggest"]
    window, least = int(suggest["window"]), int(suggest["min_hedged"])
    hedges = tuple(str(h) for h in suggest["hedges"])
    if not 1 <= least <= window or not hedges:
        raise ValueError("style suggestion needs 1 <= min_hedged <= window and some hedges")
    return Framing(
        {k: str(v) for k, v in raw["directness"].items()},
        {k: str(v) for k, v in raw["formality"].items()},
        window,
        least,
        hedges,
        str(raw["version"]),
    )


@functools.cache
def load_framing() -> Framing:
    return parse_framing(load_yaml("style", "framing.yaml"))


def framing(style: StyleProfile) -> str:
    """One "Style:" line, or "" for the default profile."""
    cfg = load_framing()
    parts = [cfg.directness[style.directness], cfg.formality[style.formality]]
    text = " ".join(p for p in parts if p)
    return STYLE_MARK + text if text else ""
