"""Psychoeducation items: loading, content checks and selection (FR-PSY).

A separate content path from the therapy exercises (FR-PSY-1). Whether a message is a cue
at all is the `psychoed` scorer in content/lexicons/cues.yaml; this module only picks the
vetted item that answers it. Items are tried in file order, so specific topics come before
broad ones, and the one item without cues (the general item, listed last) answers the rest.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from oasis.content import REVIEW, load_yaml, require_review
from oasis.safety.normalize import base_form

MAX_GRADE = 8.0  # Flesch-Kincaid grade ceiling for every item (CR-13)
_FIELDS = ("id", "topic", "text", "source", "version")
_WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")
_VOWEL_GROUP = re.compile(r"[aeiouy]+")
_SENTENCE_END = re.compile(r"[.!?]+")


@dataclass(frozen=True)
class Item:
    id: str
    topic: str
    text: str
    reading_level: float
    cues: tuple[re.Pattern[str], ...]
    source: str
    version: str
    review_status: str


def _syllables(word: str) -> int:
    # ponytail: vowel-group heuristic, within about one syllable on plain English; use a
    # pronunciation dictionary if the grade check ever needs to be exact.
    n = len(_VOWEL_GROUP.findall(word))
    if n > 1 and word.endswith("e") and not word.endswith(("le", "ee")):
        n -= 1  # silent final e
    return max(1, n)


def reading_grade(text: str) -> float:
    """Flesch-Kincaid grade level of `text`."""
    words = _WORD.findall(text.lower())
    if not words:
        return 0.0
    sentences = max(1, len(_SENTENCE_END.findall(text)))
    syllables = sum(_syllables(w) for w in words)
    return 0.39 * len(words) / sentences + 11.8 * syllables / len(words) - 15.59


def _item(raw: Mapping[str, Any]) -> Item:
    name = f"psychoed item {raw.get('id')}"
    if not all(isinstance(raw.get(f), str) and raw[f] for f in _FIELDS):
        raise ValueError(f"{name}: needs {', '.join(_FIELDS)}")
    require_review(raw, name)
    if not isinstance(raw.get("cues"), list):
        raise ValueError(f"{name}: cues must be a list")
    try:
        cues = tuple(re.compile(c) for c in raw["cues"])
    except (re.error, TypeError) as exc:
        raise ValueError(f"{name}: bad cue") from exc
    grade = round(reading_grade(raw["text"]), 1)
    if raw.get("reading_level") != grade:
        raise ValueError(f"{name}: reading_level should be {grade}")
    if grade > MAX_GRADE:
        raise ValueError(f"{name}: grade {grade} is above {MAX_GRADE}")
    return Item(raw["id"], raw["topic"], raw["text"], grade, cues, raw["source"],
                raw["version"], REVIEW)  # fmt: skip


def parse(raw: Mapping[str, Any]) -> tuple[Item, ...]:
    require_review(raw, "psychoed file")
    items = tuple(_item(r) for r in raw.get("items") or ())
    if len({i.id for i in items}) != len(items):
        raise ValueError("psychoed item ids must be unique")
    general = [i for i in items if not i.cues]
    if len(general) != 1 or items[-1] is not general[0]:
        raise ValueError("psychoed file needs exactly one general item (no cues), listed last")
    return items


@functools.cache
def load_all() -> tuple[Item, ...]:
    return parse(load_yaml("psychoed", "items.yaml"))


def select(message: str, shown: Collection[str]) -> Item | None:
    """The first item not yet shown whose cues match; None once the general item is used."""
    norm = base_form(message)
    fresh = (i for i in load_all() if i.id not in shown)
    return next((i for i in fresh if not i.cues or any(c.search(norm) for c in i.cues)), None)
